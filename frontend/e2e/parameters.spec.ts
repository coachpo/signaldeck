import { expect, test } from "@playwright/test";
import { stringify } from "yaml";
import { apiBase, seed } from "./platform-fixtures";
test("array input uses the same definition for manual and scheduled launches without an object wrapper", async ({
  page,
  request,
}) => {
  const { key, model } = await seed(request);
  const array = { type: "array", items: { type: "string" } };
  const source = stringify(
    {
      apiVersion: "signaldeck.workflowPackage/v2",
      metadata: { key, name: `Array ${key}` },
      agents: {
        reader: {
          inputSchema: array,
          outputSchema: { type: "string" },
          strategy: {
            kind: "model",
            modelRef: model,
            prompt: "Return a JSON string describing the supplied array.",
          },
        },
      },
      workflows: {
        main: {
          name: "Array workflow",
          inputSchema: array,
          outputSchema: { type: "string" },
          nodes: {
            consume: {
              uses: "reader",
              inputMapping: { ref: "workflow.input" },
            },
          },
          outputMapping: { ref: "nodes.consume.output" },
        },
      },
    },
    { aliasDuplicateObjects: false },
  );
  const saved = await request.patch(`${apiBase}/workflow-packages/${key}`, {
    data: { manifestSource: source },
  });
  expect(saved.ok(), await saved.text()).toBeTruthy();
  await page.goto("/tasks");
  const card = page.locator("section").filter({
    has: page.getByRole("heading", { name: "Array workflow", exact: true }),
  }).last();
  await card.getByRole("link", { name: "选择任务", exact: true }).click();
  await expect(
    page.getByRole("tab", { name: "填写输入", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("任务输入 JSON")).toHaveValue("[]");
  await page.getByLabel("任务输入 JSON").fill('["alpha","beta"]');
  await page.getByRole("button", { name: "应用 JSON 输入" }).click();
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/[^/]+$/);
  const manualId = page.url().split("/").at(-1)!;
  await expect
    .poll(
      async () =>
        (await (await request.get(`${apiBase}/runs/${manualId}`)).json())
          .status,
      { timeout: 60000 },
    )
    .toBe("succeeded");
  await page
    .getByRole("link", { name: "技术详情与调用证据", exact: true })
    .click();
  await page
    .getByRole("tab", { name: "Immutable snapshot", exact: true })
    .click();
  expect(
    JSON.parse(
      await page.getByLabel("Frozen run specification JSON").inputValue(),
    ).parameters,
  ).toEqual(["alpha", "beta"]);
  await page.goto("/scheduled-tasks/new");
  await page.getByLabel("安排名称").fill(`Array schedule ${key}`);
  await page.getByRole("combobox", { name: "选择任务", exact: true }).click();
  await page
    .getByRole("option", { name: "Array workflow", exact: true })
    .click();
  await page.getByLabel("任务输入 JSON", { exact: true }).fill("[]");
  await page
    .getByRole("button", { name: "应用 JSON 输入", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "自动执行状态", exact: true })
    .click();
  await page.getByRole("option", { name: "已暂停", exact: true }).click();
  const saving = page.waitForResponse(
    (response) =>
      response.url() === `${apiBase}/schedules` &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "启用自动执行", exact: true }).click();
  const created = await saving;
  expect(created.ok(), await created.text()).toBeTruthy();
  const scheduleId = (await created.json()).id as string;
  await expect(page).toHaveURL(`/scheduled-tasks/${scheduleId}`);
  await expect
    .poll(
      async () =>
        (await (await request.get(`${apiBase}/schedules/${scheduleId}`)).json())
          .syncStatus,
      { timeout: 30000 },
    )
    .toBe("synced");
  expect(
    (await (await request.get(`${apiBase}/schedules/${scheduleId}`)).json())
      .parameters,
  ).toEqual([]);
  await page.getByRole("button", { name: "立即执行", exact: true }).click();
  await expect(page.getByText("已接受执行请求", { exact: true })).toBeVisible();
  let scheduledId = "";
  await expect
    .poll(
      async () => {
        const run = (
          await (await request.get(`${apiBase}/runs`)).json()
        ).items.find(
          (item: { origin: { scheduleId?: string } }) =>
            item.origin.scheduleId === scheduleId,
        );
        scheduledId = run?.id ?? "";
        return run?.status;
      },
      { timeout: 60000 },
    )
    .toBe("succeeded");
  const detail = await (
    await request.get(`${apiBase}/runs/${scheduledId}`)
  ).json();
  expect(detail.spec.parameters).toEqual([]);
  expect(detail.origin.scheduleId).toBe(scheduleId);
});
