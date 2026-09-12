import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { parse, stringify } from "yaml";
import { apiBase, seed } from "./platform-fixtures";
const evidenceDirectory = resolve("../output/playwright/schedule-experience");
async function recordEvidence(
  testInfo: TestInfo,
  name: string,
  evidence: unknown,
) {
  mkdirSync(evidenceDirectory, { recursive: true });
  const body = JSON.stringify(
    {
      observedAt: new Date().toISOString(),
      test: testInfo.title,
      environment:
        "Owned local PostgreSQL/Temporal stack with controlled provider; not external supplier validation",
      evidence,
    },
    null,
    2,
  );
  const path = resolve(evidenceDirectory, `${name}.json`);
  writeFileSync(path, body);
  await testInfo.attach(`${name}.json`, {
    path,
    contentType: "application/json",
  });
}
async function captureOrdinarySchedule(
  page: Page,
  testInfo: TestInfo,
  name: string,
) {
  mkdirSync(evidenceDirectory, { recursive: true });
  await expect(
    page.getByRole("switch", { name: "专家模式" }),
  ).not.toBeChecked();
  for (const width of [375, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    await expect
      .poll(() =>
        page.evaluate(
          () => document.documentElement.scrollWidth <= window.innerWidth,
        ),
      )
      .toBe(true);
    const path = resolve(evidenceDirectory, `${name}-${width}.png`);
    await page.screenshot({ path, fullPage: true });
    await testInfo.attach(`${name}-${width}.png`, {
      path,
      contentType: "image/png",
    });
  }
}
test.use({ timezoneId: "UTC" });
test("schedule retains timezone, overlap, synchronization state and trigger provenance", async ({
  page,
  request,
}, testInfo) => {
  const { key } = await seed(request);
  const name = `Schedule ${key}`;
  const created = await request.post(`${apiBase}/schedules`, {
    data: {
      name,
      packageKey: key,
      workflowKey: "main",
      parameters: { summary: "Scheduled evidence" },
      cron: "0 9 * * *",
      timeZone: "UTC",
      overlapPolicy: "buffer_one",
      catchupWindowSeconds: 60,
      paused: true,
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const schedule = await created.json();
  await page.goto(`/scheduled-tasks/${schedule.id}`);
  await page.getByLabel("时区", { exact: true }).fill("Europe/Helsinki");
  await page.getByRole("button", { name: "保存安排" }).click();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${apiBase}/schedules/${schedule.id}`)
          ).json()
        ).timeZone,
    )
    .toBe("Europe/Helsinki");
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${apiBase}/schedules/${schedule.id}`)
          ).json()
        ).syncStatus,
      { timeout: 30000 },
    )
    .toBe("synced");
  await page.reload();
  await expect(page.getByText("安排已生效", { exact: true })).toBeVisible();
  const triggerResponse = page.waitForResponse(
    (response) =>
      response.url() === `${apiBase}/schedules/${schedule.id}/trigger` &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "立即执行", exact: true }).click();
  const triggerReceipt = await (await triggerResponse).json();
  await expect(page.getByText("已接受执行请求", { exact: true })).toBeVisible();
  let runId = "";
  await expect
    .poll(
      async () => {
        const runs = (await (await request.get(`${apiBase}/runs`)).json())
          .items;
        const run = runs.find(
          (r: { origin: { scheduleId: string } }) =>
            r.origin.scheduleId === schedule.id,
        );
        runId = run?.id ?? "";
        return run?.status;
      },
      { timeout: 60000 },
    )
    .toBe("succeeded");
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${apiBase}/schedules/${schedule.id}/fires`)
          ).json()
        ).items[0]?.status,
      { timeout: 30000 },
    )
    .toBe("succeeded");
  const appliedSchedule = await (
    await request.get(`${apiBase}/schedules/${schedule.id}`)
  ).json();
  const appliedPreviewResponse = await request.get(
    `${apiBase}/schedules/${schedule.id}/preview`,
  );
  expect(
    appliedPreviewResponse.ok(),
    await appliedPreviewResponse.text(),
  ).toBeTruthy();
  const appliedPreview = await appliedPreviewResponse.json();
  expect(appliedPreview.scope).toBe("applied");
  expect(appliedPreview.desiredRevision).toBe(appliedSchedule.revision);
  expect(appliedPreview.syncedRevision).toBe(appliedSchedule.syncedRevision);
  const firesBeforeDeletion = await (
    await request.get(`${apiBase}/schedules/${schedule.id}/fires`)
  ).json();
  await page.getByRole("button", { name: "删除安排", exact: true }).click();
  await page.getByRole("alertdialog", { name: "删除这个安排？", exact: true }).getByRole("button", { name: "删除", exact: true }).click();
  await expect(page).toHaveURL("/scheduled-tasks");
  const run = await (await request.get(`${apiBase}/runs/${runId}`)).json();
  expect(run.origin.scheduleId).toBe(schedule.id);
  expect(run.origin.triggerId).toBeTruthy();
  const retainedFires = await (
    await request.get(`${apiBase}/schedules/${schedule.id}/fires`)
  ).json();
  expect(
    retainedFires.items.some(
      (fire: { runId: string }) => fire.runId === run.id,
    ),
  ).toBe(true);
  await recordEvidence(testInfo, "schedule-success-and-retained-provenance", {
    createdSchedule: schedule,
    appliedSchedule,
    triggerReceipt,
    appliedPreview,
    firesBeforeDeletion,
    retainedFires,
    run,
  });
});

test("failed scheduled launch retains provenance with a readable failure reason", async ({
  page,
  request,
}, testInfo) => {
  const { key, source } = await seed(request);
  const created = await request.post(`${apiBase}/schedules`, {
    data: {
      name: `Failed fire ${key}`,
      packageKey: key,
      workflowKey: "main",
      parameters: { summary: "Fire failure" },
      cron: "0 9 * * *",
      timeZone: "UTC",
      overlapPolicy: "skip",
      catchupWindowSeconds: 60,
      paused: true,
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const schedule = await created.json();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${apiBase}/schedules/${schedule.id}`)
          ).json()
        ).syncStatus,
      { timeout: 30000 },
    )
    .toBe("synced");
  const definition = parse(source);
  definition.workflows = { renamed: definition.workflows.main };
  const changed = await request.patch(`${apiBase}/workflow-packages/${key}`, {
    data: {
      manifestSource: stringify(definition, { aliasDuplicateObjects: false }),
    },
  });
  expect(changed.ok(), await changed.text()).toBeTruthy();
  const fired = await request.post(
    `${apiBase}/schedules/${schedule.id}/trigger`,
    { data: { triggerId: crypto.randomUUID() } },
  );
  expect(fired.ok(), await fired.text()).toBeTruthy();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${apiBase}/schedules/${schedule.id}/fires`)
          ).json()
        ).items[0]?.status,
      { timeout: 60000 },
    )
    .toBe("launch_failed");
  await page.goto(`/scheduled-tasks/${schedule.id}`);
  await expect(page.getByText("未能启动", { exact: true })).toBeVisible();
  await expect(page.getByText("找不到工作流。请检查安排中的任务选择。", { exact: true })).toBeVisible();
  await expect(page.getByText("workflow_not_found", { exact: true })).not.toBeVisible();
  await expect(page.getByText("原始错误码", { exact: true })).toHaveCount(0);
  await expect(page.getByText(/Engine workflow|execution engine|Fire [a-f0-9-]/)).toHaveCount(0);
  await expect(page.getByText("尚未生成结果", { exact: true })).toBeVisible();
  const records = await (
    await request.get(`${apiBase}/schedules/${schedule.id}/fires`)
  ).json();
  expect(records.items[0].engineRunId).toBeTruthy();
  expect(records.items[0].triggerId).toBeTruthy();
  expect(records.items[0].runId).toBeNull();
  const appliedSchedule = await (
    await request.get(`${apiBase}/schedules/${schedule.id}`)
  ).json();
  const appliedPreviewResponse = await request.get(
    `${apiBase}/schedules/${schedule.id}/preview`,
  );
  expect(
    appliedPreviewResponse.ok(),
    await appliedPreviewResponse.text(),
  ).toBeTruthy();
  await recordEvidence(testInfo, "schedule-failed-launch-provenance", {
    appliedSchedule,
    triggerReceipt: await fired.json(),
    fires: records,
    appliedPreview: await appliedPreviewResponse.json(),
  });
});

test("weekly preview and custom schedules preserve business input and advanced policy across modes", async ({
  page,
  request,
}, testInfo) => {
  const { key } = await seed(request);
  const created = await request.post(`${apiBase}/schedules`, {
    data: {
      name: `Weekly ${key}`,
      packageKey: key,
      workflowKey: "main",
      parameters: { summary: "Keep this business information" },
      cron: "30 9 * * 1",
      timeZone: "Europe/Helsinki",
      overlapPolicy: "buffer_one",
      catchupWindowSeconds: 180,
      paused: true,
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const schedule = await created.json();
  await page.goto(`/scheduled-tasks/${schedule.id}`);
  await expect(
    page.getByText("每周一 09:30 · Europe/Helsinki.", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "预览下次时间", exact: true }).click();
  await expect(page.getByText("时间预览，不会启用自动执行")).toBeVisible();
  const preview = await request.post(`${apiBase}/schedules/preview`, {
    data: { cron: "30 9 * * 1", timeZone: "Europe/Helsinki" },
  });
  expect(preview.ok(), await preview.text()).toBeTruthy();
  const draftPreview = await preview.json();
  const times = draftPreview.times;
  expect(times).toHaveLength(5);
  for (const time of times) {
    const local = new Intl.DateTimeFormat("en-GB", {
      timeZone: "Europe/Helsinki",
      weekday: "long",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(time));
    expect(local).toContain("Monday");
    expect(local).toContain("09:30");
  }
  const weeklySchedule = await (
    await request.get(`${apiBase}/schedules/${schedule.id}`)
  ).json();
  const weeklyAppliedPreviewResponse = await request.get(
    `${apiBase}/schedules/${schedule.id}/preview`,
  );
  expect(
    weeklyAppliedPreviewResponse.ok(),
    await weeklyAppliedPreviewResponse.text(),
  ).toBeTruthy();
  const weeklyAppliedPreview = await weeklyAppliedPreviewResponse.json();
  await captureOrdinarySchedule(page, testInfo, "weekly-ordinary");
  await page.getByRole("combobox", { name: "重复频率", exact: true }).click();
  await page.getByRole("option", { name: "组合日期与时刻", exact: true }).click();
  await page.getByRole("combobox", { name: "执行小时范围", exact: true }).click();
  await page.getByRole("option", { name: "选择多个或按间隔", exact: true }).click();
  await page.getByRole("checkbox", { name: "执行小时 8时", exact: true }).check();
  await page.getByRole("checkbox", { name: "执行小时 17时", exact: true }).check();
  await page.getByRole("checkbox", { name: "执行小时 9时", exact: true }).uncheck();
  await page.getByRole("combobox", { name: "每小时的分钟选择", exact: true }).click();
  await page.getByRole("option", { name: "0分", exact: true }).click();
  await page.getByRole("combobox", { name: "执行星期范围", exact: true }).click();
  await page.getByRole("option", { name: "选择多个或按间隔", exact: true }).click();
  for (const day of ["周二", "周三", "周四", "周五"]) {
    await page.getByRole("checkbox", { name: `执行星期 ${day}`, exact: true }).check();
  }
  await page.getByLabel("安排名称").fill(`Custom ${key}`);
  await page.getByRole("switch", { name: "专家模式" }).click();
  await expect(page.getByLabel("上一次尚未结束时")).toContainText("保留一次");
  await page.getByRole("switch", { name: "专家模式" }).click();
  await expect(page.getByLabel("自定义时间表达式")).toHaveCount(0);
  await expect(page.getByText(/SignalDeck revision|调度服务|待应用版本|技术来源/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "立即执行", exact: true })).toBeDisabled();
  await page.getByRole("link", { name: "自动执行", exact: true }).first().click();
  await page.getByRole("link", { name: `查看 Weekly ${key}`, exact: true }).click();
  await expect(page.getByLabel("安排名称")).toHaveValue(`Custom ${key}`);
  await expect(page.getByRole("checkbox", { name: "执行小时 17时", exact: true })).toBeChecked();
  await page.getByRole("button", { name: "保存安排", exact: true }).click();
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${apiBase}/schedules/${schedule.id}`)
          ).json()
        ).cron,
    )
    .toBe("0 8,17 * * 1-5");
  const stored = await (
    await request.get(`${apiBase}/schedules/${schedule.id}`)
  ).json();
  expect(stored.parameters).toEqual({
    summary: "Keep this business information",
  });
  expect(stored.timeZone).toBe("Europe/Helsinki");
  expect(stored.overlapPolicy).toBe("buffer_one");
  expect(stored.catchupWindowSeconds).toBe(180);
  expect(stored.paused).toBe(true);
  await expect
    .poll(
      async () =>
        (
          await (
            await request.get(`${apiBase}/schedules/${schedule.id}`)
          ).json()
        ).syncStatus,
      { timeout: 30000 },
    )
    .toBe("synced");
  const customSchedule = await (
    await request.get(`${apiBase}/schedules/${schedule.id}`)
  ).json();
  const customPreviewResponse = await request.get(
    `${apiBase}/schedules/${schedule.id}/preview`,
  );
  expect(
    customPreviewResponse.ok(),
    await customPreviewResponse.text(),
  ).toBeTruthy();
  const customAppliedPreview = await customPreviewResponse.json();
  expect(customAppliedPreview.desiredRevision).toBe(customSchedule.revision);
  expect(customAppliedPreview.syncedRevision).toBe(
    customSchedule.syncedRevision,
  );
  expect(customAppliedPreview.times.length).toBeGreaterThan(0);
  await page.reload();
  await expect(page.getByText("安排已生效", { exact: true })).toBeVisible();
  await expect(
    page.getByText("已暂停，以下仅供核对时间，不会自动执行"),
  ).toBeVisible();
  await captureOrdinarySchedule(page, testInfo, "custom-ordinary");
  await recordEvidence(testInfo, "schedule-weekly-and-custom-preview", {
    weeklySchedule,
    draftPreview,
    weeklyAppliedPreview,
    customSchedule,
    customAppliedPreview,
    screenshots: [
      "weekly-ordinary-375.png",
      "weekly-ordinary-1440.png",
      "custom-ordinary-375.png",
      "custom-ordinary-1440.png",
    ],
  });
  await request.delete(`${apiBase}/schedules/${schedule.id}`);
});
