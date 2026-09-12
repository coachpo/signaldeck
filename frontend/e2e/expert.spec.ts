import { expect, test, type Page, type TestInfo } from "@playwright/test";
import { parse } from "yaml";
import { readFile, mkdir, writeFile, copyFile } from "node:fs/promises";
import { resolve } from "node:path";
import { apiBase, seed } from "./platform-fixtures";

const evidenceDirectory = resolve("../output/playwright/expert-experience");
async function screenshot(page: Page, testInfo: TestInfo, name: string) {
  await mkdir(evidenceDirectory, { recursive: true });
  const buffer = await page.screenshot({ path: testInfo.outputPath(name), fullPage: true, animations: "disabled" });
  await writeFile(resolve(evidenceDirectory, name), buffer);
}
async function roundtrip(page: Page) {
  const mode = page.getByRole("switch", { name: "专家模式", exact: true });
  await mode.check(); await mode.uncheck(); await mode.check();
}

test("expert authors with named controls, keeps session drafts and fixes invalid step order", async ({ page, request }, testInfo) => {
  const { key, pkg } = await seed(request);
  const userInstructions = "Return a short verified summary.\nKeep this example unchanged:\n```js\nconst threshold = 0;\n```\n";
  await page.goto(`/workflow-packages/${key}`);
  await page.getByRole("button", { name: "Reusable analyst", exact: true }).click();
  await page.getByLabel("助手任务说明", { exact: true }).fill(userInstructions);
  await page.getByLabel("总模型用量上限（模型计量单位）", { exact: true }).fill("4567");
  await roundtrip(page);
  await expect(page.getByLabel("助手任务说明", { exact: true })).toHaveValue(userInstructions);
  await expect(page.getByLabel("总模型用量上限（模型计量单位）", { exact: true })).toHaveValue("4567");
  await page.getByRole("link", { name: "开始任务", exact: true }).click();
  await page.getByRole("button", { name: "保留草稿并离开", exact: true }).click();
  await expect(page).toHaveURL(`/workflow-packages/${key}/run`);
  await page.goBack();
  await expect(page.getByLabel("助手任务说明", { exact: true })).toHaveValue(userInstructions);
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await page.getByRole("button", { name: "保存工作流", exact: true }).scrollIntoViewIfNeeded();
    const bounds = await page.getByRole("button", { name: "保存工作流", exact: true }).boundingBox();
    expect(bounds).not.toBeNull(); expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width);
    await screenshot(page, testInfo, `expert-properties-${width}.png`);
  }
  await page.getByRole("button", { name: "检查工作流", exact: true }).click();
  await expect(page.getByText("检查通过，可以保存并开始任务", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "步骤关系", exact: true }).click();
  for (const label of ["等待完成", "使用结果", "根据结果判断"]) await expect(page.getByRole("list", { name: "步骤之间的关系" }).getByText(label, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "放大图", exact: true }).click();
  await expect(page.getByLabel("图缩放")).toHaveText("125%");
  await page.setViewportSize({ width: 768, height: 800 });
  const viewport = page.getByRole("region", { name: "任务步骤" });
  await viewport.focus(); await viewport.press("ArrowRight");
  await page.getByRole("button", { name: "自动布局 / 适合窗口", exact: true }).click();
  expect(await viewport.evaluate((element) => element.scrollLeft)).toBe(0);
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.getByRole("button", { name: "自动布局 / 适合窗口", exact: true }).click();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    await screenshot(page, testInfo, `expert-graph-${width}.png`);
  }
  await expect(page.getByText(/nodes\.second\.condition|dependency readiness|Agent definitions/)).toHaveCount(0);
  await page.getByRole("button", { name: "保存工作流", exact: true }).click();
  await expect(page.getByText("工作流已保存", { exact: true })).toBeVisible();
  const saved = await (await request.get(`${apiBase}/workflow-packages/${key}`)).json();
  expect(saved.definition.agents.analyst.budget.maxTokens).toBe(4567);
  expect(saved.definition.agents.analyst.strategy.prompt).toBe(userInstructions);
  expect(parse(saved.source).agents.analyst.strategy.prompt).toBe(userInstructions);
  expect(saved.definition.workflows).toEqual(pkg.definition.workflows);
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出工作流", exact: true }).click();
  const download = await downloadPromise;
  const exportPath = testInfo.outputPath("expert-export.yaml"); await download.saveAs(exportPath);
  await copyFile(exportPath, resolve(evidenceDirectory, "expert-export.yaml"));
  expect(parse(await readFile(exportPath, "utf8")).agents.analyst.budget.maxTokens).toBe(4567);
  await page.getByLabel("选择导入文件", { exact: true }).setInputFiles({ name: "expert.yaml", mimeType: "application/yaml", buffer: Buffer.from(`# Imported expert draft\n${saved.source}`) });
  await page.getByRole("button", { name: "替换当前草稿", exact: true }).click();
  await page.getByRole("button", { name: "步骤 1 · Reusable analyst", exact: true }).click();
  await page.getByRole("combobox", { name: "交给助手的信息 · 来源", exact: true }).click();
  await page.getByRole("option", { name: "步骤 2 · Reusable analyst的结果", exact: true }).click();
  await page.getByRole("button", { name: "检查工作流", exact: true }).click();
  await expect(page.getByText(/这些步骤互相等待/).first()).toBeVisible();
  await page.getByRole("button", { name: "Main workflow · 步骤 1 · Reusable analyst · 输入来源", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "交给助手的信息 · 来源", exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "交给助手的信息 · 来源", exact: true }).click();
  await page.getByRole("option", { name: "用户填写的信息", exact: true }).click();
  const draftDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出工作流", exact: true }).click();
  const draftDownload = await draftDownloadPromise;
  const draftPath = testInfo.outputPath("expert-imported-draft.yaml");
  await draftDownload.saveAs(draftPath);
  const draftSource = await readFile(draftPath, "utf8");
  expect(draftSource).toContain("# Imported expert draft");
  expect(parse(draftSource).agents.analyst.strategy.prompt).toBe(userInstructions);
  await page.getByRole("button", { name: "保存工作流", exact: true }).click();
  await expect(page.getByText("工作流已保存", { exact: true })).toBeVisible();
  const afterSave = await (await request.get(`${apiBase}/workflow-packages/${key}`)).json();
  expect(afterSave.source).toBe(saved.source);
  expect(afterSave.packageHash).toBe(saved.packageHash);
  expect(afterSave.definition).toEqual(saved.definition);
  expect(afterSave.plans).toEqual(saved.plans);
  expect(parse(afterSave.source).agents.analyst.strategy.prompt).toBe(userInstructions);
  await page.reload();
  await expect(page.getByLabel("工作流集名称", { exact: true })).toHaveValue(pkg.name);
});
