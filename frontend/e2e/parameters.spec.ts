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
  await page.goto(`/workflow-packages/${key}/run`);
  await page.getByRole("combobox", { name: "Workflow", exact: true }).click();
  await page
    .getByRole("option", { name: "Array workflow", exact: true })
    .click();
  await expect(
    page.getByRole("tab", { name: "Input form", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("Parameters JSON")).toHaveValue("[]");
  await page.getByLabel("Parameters JSON").fill('["alpha","beta"]');
  await page.getByRole("button", { name: "Apply parameters JSON" }).click();
  await page.getByRole("button", { name: "Start run", exact: true }).click();
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
    .getByRole("tab", { name: "Immutable snapshot", exact: true })
    .click();
  expect(
    JSON.parse(
      await page.getByLabel("Frozen run specification JSON").inputValue(),
    ).parameters,
  ).toEqual(["alpha", "beta"]);
  await page.goto("/scheduled-tasks/new");
  await page.getByLabel("Schedule name").fill(`Array schedule ${key}`);
  await page.getByRole("combobox", { name: "Package", exact: true }).click();
  await page.getByRole("option", { name: `Array ${key}`, exact: true }).click();
  await page.getByRole("combobox", { name: "Workflow", exact: true }).click();
  await page
    .getByRole("option", { name: "Array workflow", exact: true })
    .click();
  await page.getByLabel("Schedule parameters JSON").fill("[]");
  await page
    .getByRole("combobox", { name: "Schedule status", exact: true })
    .click();
  await page.getByRole("option", { name: "Paused", exact: true }).click();
  const saving = page.waitForResponse(
    (response) =>
      response.url() === `${apiBase}/schedules` &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Save schedule", exact: true })
    .click();
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
  await page.getByRole("button", { name: "Run now", exact: true }).click();
  await expect(
    page.getByText("Trigger accepted", { exact: true }),
  ).toBeVisible();
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
