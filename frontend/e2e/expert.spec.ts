import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { parse } from "yaml";
import { readFile, mkdir, writeFile, copyFile } from "node:fs/promises";
import { resolve } from "node:path";
import { apiBase, seed } from "./platform-fixtures";

const evidenceDirectory = resolve("../output/playwright/expert-experience");
async function screenshot(page: Page, testInfo: TestInfo, name: string) {
  await mkdir(evidenceDirectory, { recursive: true });
  const buffer = await page.screenshot({
    path: testInfo.outputPath(name),
    fullPage: true,
    animations: "disabled",
  });
  await writeFile(resolve(evidenceDirectory, name), buffer);
}

async function roundtrip(page: Page) {
  const mode = page.getByRole("switch", { name: "专家模式", exact: true });
  await mode.check();
  await mode.uncheck();
  await mode.check();
}

test("UX07 UX08 expert attributes, pending mappings, YAML diagnostics and graph viewport share one draft", async ({
  page,
  request,
}, testInfo) => {
  const { key, pkg } = await seed(request);
  const source = pkg.source as string;
  await page.goto(`/workflow-packages/${key}`);
  await page.getByRole("tab", { name: "Structure", exact: true }).click();
  await page
    .getByRole("button", { name: "Agent · analyst", exact: true })
    .click();
  await page
    .getByLabel("Prompt", { exact: true })
    .fill("Return a short verified summary.");
  await page.getByLabel("maxTokens", { exact: true }).fill("4567");
  await roundtrip(page);
  await expect(page.getByLabel("Prompt", { exact: true })).toHaveValue(
    "Return a short verified summary.",
  );
  await expect(page.getByLabel("maxTokens", { exact: true })).toHaveValue(
    "4567",
  );
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    const saveBounds = await page
      .getByRole("button", { name: "Save package", exact: true })
      .boundingBox();
    expect(saveBounds).not.toBeNull();
    expect(saveBounds!.x + saveBounds!.width).toBeLessThanOrEqual(width);
    await page
      .getByRole("tab", { name: "Structure", exact: true })
      .scrollIntoViewIfNeeded();
    await screenshot(page, testInfo, `expert-properties-${width}.png`);
  }
  await page.getByRole("button", { name: "↳ second", exact: true }).click();
  await page.getByLabel("condition", { exact: true }).fill('{"op":');
  await page
    .getByRole("button", { name: "Apply condition", exact: true })
    .click();
  await expect(
    page
      .getByRole("group", { name: "condition", exact: true })
      .getByRole("alert"),
  ).toBeVisible();
  await roundtrip(page);
  await expect(page.getByLabel("condition", { exact: true })).toHaveValue(
    '{"op":',
  );
  await expect(
    page.getByRole("button", { name: "Save package", exact: true }),
  ).toBeDisabled();
  await expect(
    page.getByRole("button", { name: "Agent · analyst", exact: true }),
  ).toBeDisabled();
  await page
    .getByRole("button", { name: "Discard condition draft", exact: true })
    .click();
  await page.getByRole("tab", { name: "YAML", exact: true }).click();
  const edited = await page.getByLabel("Workflow Package YAML").inputValue();
  const definition = parse(edited);
  expect(definition.agents.analyst.budget.maxTokens).toBe(4567);
  expect(definition.workflows).toEqual(parse(source).workflows);
  await page
    .getByRole("button", { name: "Validate graph", exact: true })
    .click();
  await expect(
    page.getByText("Definition validated", { exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Graph", exact: true }).click();
  for (const edge of ["control", "input", "condition"])
    await expect(
      page
        .getByRole("list", { name: "Dependency edges" })
        .getByText(edge, { exact: true }),
    ).toBeVisible();
  await page.getByRole("button", { name: "放大图", exact: true }).click();
  await expect(page.getByLabel("图缩放")).toHaveText("125%");
  await page.getByRole("combobox", { name: "定位节点", exact: true }).click();
  await page.getByRole("option", { name: "second", exact: true }).click();
  await page.setViewportSize({ width: 768, height: 800 });
  const viewport = page.getByRole("region", { name: "Workflow nodes" });
  await viewport.focus();
  await viewport.press("ArrowRight");
  await page
    .getByRole("button", { name: "自动布局 / 适合窗口", exact: true })
    .click();
  expect(await viewport.evaluate((element) => element.scrollLeft)).toBe(0);
  for (let i = 0; i < 4; i++)
    await page.getByRole("button", { name: "放大图", exact: true }).click();
  await viewport.scrollIntoViewIfNeeded();
  const box = (await viewport.boundingBox())!;
  await page.mouse.move(box.x + Math.min(350, box.width - 20), box.y + 220);
  await page.mouse.down();
  await page.mouse.move(box.x + 60, box.y + 220, { steps: 8 });
  await page.mouse.up();
  expect(
    await viewport.evaluate((element) => element.scrollLeft),
  ).toBeGreaterThan(0);
  await screenshot(page, testInfo, "expert-graph-pan-768.png");
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page
      .getByRole("button", { name: "自动布局 / 适合窗口", exact: true })
      .click();
    await page
      .getByRole("tab", { name: "Graph", exact: true })
      .scrollIntoViewIfNeeded();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth,
      ),
    ).toBe(true);
    await screenshot(page, testInfo, `expert-graph-${width}.png`);
  }
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.getByRole("button", { name: "Save package", exact: true }).click();
  await expect(
    page.getByText("Saved definition", { exact: true }),
  ).toBeVisible();
  expect(
    (await (await request.get(`${apiBase}/workflow-packages/${key}`)).json())
      .definition.agents.analyst.budget.maxTokens,
  ).toBe(4567);
  await page.getByRole("tab", { name: "YAML", exact: true }).click();
  const downloadPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "导出当前 YAML", exact: true })
    .click();
  const download = await downloadPromise;
  const exportPath = testInfo.outputPath("expert-export.yaml");
  await download.saveAs(exportPath);
  await copyFile(exportPath, resolve(evidenceDirectory, "expert-export.yaml"));
  expect(
    parse(await readFile(exportPath, "utf8")).agents.analyst.budget.maxTokens,
  ).toBe(4567);
  const imported = `# Imported expert draft\n${edited}`;
  await page.getByLabel("选择导入文件", { exact: true }).setInputFiles({
    name: "expert.yaml",
    mimeType: "application/yaml",
    buffer: Buffer.from(imported),
  });
  await expect(page.getByLabel("Workflow Package YAML")).toHaveValue(imported);
  await page
    .getByLabel("Workflow Package YAML")
    .fill(edited.replace("ref: workflow.input", "ref: nodes.second.output"));
  await page
    .getByRole("button", { name: "Validate graph", exact: true })
    .click();
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
});

test("UX07 advanced resources and releases keep drafts across modes without writing secrets or commands", async ({
  page,
  context,
  request,
}, testInfo) => {
  const { model } = await seed(request);
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("/resources");
  await page
    .getByRole("button", { name: `Edit ${model}`, exact: true })
    .click();
  await page
    .getByRole("button", { name: `复制资源 ID ${model}`, exact: true })
    .click();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(model);
  const configuration =
    '{"name":"Unsaved advanced model","baseUrl":"http://127.0.0.1:18081/v1","modelId":"controlled","timeoutSeconds":37}';
  await page.getByLabel("Resource configuration JSON").fill(configuration);
  const credentialDraft = '{"apiKey":"controlled-draft-not-saved"}';
  await page.getByLabel("New credentials JSON").fill(credentialDraft);
  const writes: string[] = [];
  page.on("request", (req) => {
    if (["POST", "PUT", "PATCH", "DELETE"].includes(req.method()))
      writes.push(req.url());
  });
  await roundtrip(page);
  await expect(page.getByLabel("Resource configuration JSON")).toHaveValue(
    configuration,
  );
  await expect(page.getByLabel("New credentials JSON")).toHaveValue(
    credentialDraft,
  );
  expect(
    await page.evaluate(() =>
      JSON.stringify({
        local: { ...localStorage },
        session: { ...sessionStorage },
      }),
    ),
  ).not.toContain("controlled-draft-not-saved");
  expect(writes).toEqual([]);
  await page.getByLabel("New credentials JSON").fill("");
  await screenshot(page, testInfo, "expert-resource-draft.png");
  await page.goto("/plugins");
  await page
    .getByLabel("Plugin release JSON")
    .fill('{"pluginId":"unsaved/example",');
  await roundtrip(page);
  await expect(page.getByLabel("Plugin release JSON")).toHaveValue(
    '{"pluginId":"unsaved/example",',
  );
  expect(writes).toEqual([]);
  await screenshot(page, testInfo, "expert-plugin-draft.png");
});
