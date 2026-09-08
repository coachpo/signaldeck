import { expect, test } from "@playwright/test";
import { parse, stringify } from "yaml";
import { apiBase, seed } from "./platform-fixtures";
test.use({ timezoneId: "UTC" });
test("schedule retains timezone, overlap, synchronization state and trigger provenance", async ({
  page,
  request,
}) => {
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
  await page.getByLabel("IANA timezone").fill("Europe/Helsinki");
  await page.getByRole("button", { name: "Save schedule" }).click();
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
  await expect(
    page.getByText("Schedule synced", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Run now", exact: true }).click();
  await expect(
    page.getByText("Trigger accepted", { exact: true }),
  ).toBeVisible();
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
  await page
    .getByRole("button", { name: "Delete schedule", exact: true })
    .click();
  await page.getByRole("button", { name: "Delete", exact: true }).click();
  await expect(page).toHaveURL("/scheduled-tasks");
  const run = await (await request.get(`${apiBase}/runs/${runId}`)).json();
  expect(run.origin.scheduleId).toBe(schedule.id);
  expect(run.origin.triggerId).toBeTruthy();
});

test("failed scheduled launch retains a visible fire identity and failure reason", async ({
  page,
  request,
}) => {
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
  await expect(page.getByText("launch_failed", { exact: true })).toBeVisible();
  await expect(
    page.getByText("workflow_not_found", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Run not created", { exact: true }),
  ).toBeVisible();
  const records = await (
    await request.get(`${apiBase}/schedules/${schedule.id}/fires`)
  ).json();
  expect(records.items[0].engineRunId).toBeTruthy();
  expect(records.items[0].triggerId).toBeTruthy();
  expect(records.items[0].runId).toBeNull();
});
