import { expect, test } from "@playwright/test";
import { parse } from "yaml";
import { apiBase, packageSource, seed } from "./platform-fixtures";
test("YAML and structure persist one definition and graph displays all edge sources", async ({
  page,
  request,
}, testInfo) => {
  const { key, model } = await seed(request);
  const nextKey = `${key}-editor`;
  await page.goto("/workflow-packages/new");
  await page
    .getByLabel("Workflow Package YAML")
    .fill(packageSource(nextKey, model));
  await page.getByRole("tab", { name: "Structure", exact: true }).click();
  await page
    .getByLabel("Package name", { exact: true })
    .fill("Edited in structure");
  await page.getByRole("tab", { name: "YAML", exact: true }).click();
  expect(
    parse(await page.getByLabel("Workflow Package YAML").inputValue()).metadata
      .name,
  ).toBe("Edited in structure");
  await page.getByRole("button", { name: "Validate graph" }).click();
  await expect(
    page.getByText("Definition validated", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Graph", exact: true }).click();
  await expect(page.getByText("first → second")).toBeVisible();
  for (const source of ["control", "input", "condition"])
    await expect(page.getByText(source, { exact: true })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("definition-graph.png"),
    fullPage: true,
    animations: "disabled",
  });
  await page.getByRole("button", { name: "Save package" }).click();
  await expect(page).toHaveURL(`/workflow-packages/${nextKey}`);
  const persisted = await request.get(
    `${apiBase}/workflow-packages/${nextKey}`,
  );
  expect((await persisted.json()).definition.metadata.name).toBe(
    "Edited in structure",
  );
});
test("invalid references and cycles show diagnostics without persisting invalid source", async ({
  page,
  request,
}) => {
  const { key, source } = await seed(request);
  await page.goto(`/workflow-packages/${key}`);
  const invalid = source.replace(
    "ref: workflow.input",
    "ref: nodes.second.output",
  );
  await page.getByLabel("Workflow Package YAML").fill(invalid);
  await page.getByRole("button", { name: "Validate graph" }).click();
  await expect(page.getByText("Definition needs attention")).toBeVisible();
  await expect(page.getByText(/dependency_cycle:/).first()).toBeVisible();
  await page
    .getByRole("button", { name: /nodes.first.inputMapping.ref/ })
    .click();
  await expect(page.getByLabel("Workflow Package YAML")).toBeFocused();
  expect(
    await page
      .getByLabel("Workflow Package YAML")
      .evaluate((element: HTMLTextAreaElement) => element.selectionStart),
  ).toBeGreaterThan(0);
  const persisted = await request.get(`${apiBase}/workflow-packages/${key}`);
  expect((await persisted.json()).source).not.toBe(invalid);
});
test("launch validates applied inputs and retained evidence survives browser closure", async ({
  page,
  context,
  request,
}, testInfo) => {
  const { key } = await seed(request);
  await page.goto(`/workflow-packages/${key}/run`);
  await expect(page.getByRole("button", { name: "Start run" })).toBeDisabled();
  await page.getByRole("combobox", { name: "Workflow", exact: true }).click();
  await page.getByRole("option", { name: "Main workflow" }).click();
  await page.getByRole("tab", { name: "Advanced JSON", exact: true }).click();
  await page
    .getByLabel("Parameters JSON")
    .fill('{"summary":"Launch evidence"}');
  await expect(page.getByRole("button", { name: "Start run" })).toBeDisabled();
  await page.getByRole("button", { name: "Apply parameters JSON" }).click();
  await page.getByRole("button", { name: "Start run" }).click();
  await expect(page).toHaveURL(/\/runs\/[^/]+$/);
  const runId = page.url().split("/").at(-1)!;
  await page.close();
  await expect
    .poll(
      async () =>
        (await (await request.get(`${apiBase}/runs/${runId}`)).json()).status,
      { timeout: 60000 },
    )
    .toBe("succeeded");
  const inspection = await context.newPage();
  await inspection.goto(`/runs/${runId}`);
  await inspection.getByRole("tab", { name: "Call evidence" }).click();
  await expect(inspection.getByLabel("Call ownership tree")).toBeVisible();
  await expect(
    inspection.getByRole("link", { name: /agent · first/ }).first(),
  ).toBeVisible();
  await inspection.screenshot({
    path: testInfo.outputPath("call-evidence.png"),
    fullPage: true,
    animations: "disabled",
  });
  await inspection.getByRole("tab", { name: "Immutable snapshot" }).click();
  const snapshot = JSON.parse(
    await inspection.getByLabel("Frozen run specification JSON").inputValue(),
  );
  expect(snapshot.parameters).toEqual({ summary: "Launch evidence" });
  expect(JSON.stringify(snapshot)).not.toContain("fake-local-key");
  await inspection
    .getByRole("button", { name: "Rerun frozen snapshot" })
    .click();
  await expect(inspection).not.toHaveURL(new RegExp(`${runId}$`));
});
