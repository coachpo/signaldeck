import { expect, test } from "@playwright/test";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { parse, stringify } from "yaml";
import { apiBase } from "./platform-fixtures";
import { connectTaskServices } from "./task-fixtures";
import { captureResponsiveEvidence } from "./responsive-evidence";

const directory = resolve("../output/playwright/personal-use");

test("personal workflow retains drafts and launch identity, delivers results, and organizes fixed comparisons", async ({ page, request }, testInfo) => {
  test.setTimeout(180_000);
  mkdirSync(directory, { recursive: true });
  await connectTaskServices(request, false);
  const key = `personal-${crypto.randomUUID().slice(0, 8)}`;
  const reference = parse(readFileSync(resolve("../demo/research_notes.yaml"), "utf8"));
  const workflow = reference.workflows.capture;
  workflow.name = "独立资料整理";
  workflow.inputSchema = {
    type: "object",
    properties: {
      caption: { type: "string", minLength: 1, maxLength: 200, title: "资料标题" },
      passage: { type: "string", maxLength: 100000, title: "资料正文" },
    },
    required: ["caption", "passage"],
  };
  workflow.nodes.save.inputMapping = {
    object: { title: { ref: "workflow.input.caption" }, text: { ref: "workflow.input.passage" } },
  };
  workflow.presentation.title.ref = "workflow.input.caption";
  workflow.presentation.inputHints = [
    { ref: "workflow.input.caption", control: "text" },
    { ref: "workflow.input.passage", control: "textarea" },
  ];
  const definition = {
    apiVersion: reference.apiVersion, metadata: { key, name: "独立资料包" },
    agents: { write_note: reference.agents.write_note }, workflows: { retain: workflow },
  };
  const saved = await request.post(`${apiBase}/workflow-packages`, { data: { manifestSource: stringify(definition, { aliasDuplicateObjects: false }) } });
  expect(saved.ok(), await saved.text()).toBe(true);
  const originalHash = (await saved.json()).packageHash;
  const firstInput = { caption: `${key} first`, passage: "# Confirmed original\n\n1. First item\n2. Second item\n\nA retained source." };
  await page.goto(`/tasks/new?packageKey=${key}&workflowKey=retain`);
  await page.getByLabel("资料标题", { exact: true }).fill(firstInput.caption);
  await page.getByLabel("资料正文", { exact: true }).fill(firstInput.passage);
  await page.getByRole("tab", { name: "JSON 输入", exact: true }).click();
  await page.getByLabel("任务输入 JSON", { exact: true }).fill('{"caption":');
  await page.getByLabel("草稿名称", { exact: true }).fill(`${key} unfinished`);
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page).toHaveURL(/draftId=/);
  const draftId = new URL(page.url()).searchParams.get("draftId")!;
  await page.reload();
  await expect(page.getByLabel("任务输入 JSON", { exact: true })).toHaveValue('{"caption":');
  await expect(page.getByRole("button", { name: "开始任务", exact: true })).toBeDisabled();
  const stored = await (await request.get(`${apiBase}/task-drafts/${draftId}`)).json();
  expect(stored.parameters).toEqual(firstInput);
  expect(stored.jsonText).toBe('{"caption":');
  expect(stored.packageHash).toBe(originalHash);

  workflow.inputSchema.properties = { ...workflow.inputSchema.properties, futureField: { type: "string" } };
  workflow.inputSchema.required.push("futureField");
  const changed = await request.post(`${apiBase}/workflow-packages`, { data: { manifestSource: stringify(definition, { aliasDuplicateObjects: false }) } });
  expect(changed.ok(), await changed.text()).toBe(true);
  expect((await changed.json()).packageHash).not.toBe(originalHash);
  await page.reload();
  await expect(page.getByText(/任务当前定义已更新/)).toBeVisible();
  await expect(page.getByLabel("任务输入 JSON", { exact: true })).toHaveValue('{"caption":');
  await page.getByLabel("任务输入 JSON", { exact: true }).fill(JSON.stringify(firstInput));
  await page.getByRole("button", { name: "应用 JSON 输入", exact: true }).click();
  await expect(page.getByRole("button", { name: "开始任务", exact: true })).toBeEnabled();

  const submissions: string[] = [];
  let responseLost = false;
  await page.route(`**/workflow-packages/${key}/launches`, async (route) => {
    expect(new URL(page.url()).searchParams.get("draftId")).toBe(draftId);
    submissions.push(route.request().postDataJSON().launchId);
    if (submissions.length === 1) { await route.fetch(); await route.abort("connectionfailed"); responseLost = true; }
    else await route.continue();
  });
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect.poll(() => responseLost).toBe(true);
  await expect(page.getByRole("button", { name: "使用同一请求重试", exact: true })).toBeEnabled();
  await page.reload();
  await expect(page.getByRole("button", { name: "使用同一请求重试", exact: true })).toBeEnabled();
  await expect(page.getByRole("button", { name: "保存草稿", exact: true })).toBeDisabled();
  await page.getByRole("button", { name: "使用同一请求重试", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/[^/?]+$/);
  expect(submissions).toHaveLength(2);
  expect(submissions[1]).toBe(submissions[0]);
  await page.unroute(`**/workflow-packages/${key}/launches`);
  const firstId = new URL(page.url()).pathname.split("/").at(-1)!;
  await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${firstId}`)).json()).status, { timeout: 60_000 }).toBe("succeeded");
  await page.reload();
  const firstRun = await (await request.get(`${apiBase}/runs/${firstId}`)).json();
  expect(firstRun.spec.parameters).toEqual(firstInput);
  expect(firstRun.packageHash).toBe(originalHash);
  expect((await (await request.get(`${apiBase}/runs?packageKey=${key}`)).json()).total).toBe(1);
  await expect(page.getByRole("region", { name: "笔记正文", exact: true })).toContainText("Confirmed original");
  await expect(page.getByRole("region", { name: "笔记正文", exact: true }).locator("ol")).toHaveCSS("list-style-type", "decimal");

  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 Markdown", exact: true }).click();
  const download = await downloadPromise;
  expect(await download.failure()).toBeNull();
  const file = resolve(directory, "confirmed-result.md");
  await download.saveAs(file);
  expect(readFileSync(file, "utf8")).toContain(firstInput.passage);
  expect(readFileSync(file, "utf8")).toContain(firstId);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.getByRole("button", { name: "复制所选正文", exact: true }).click();
  await expect(page.getByText("所选确认内容已复制。", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => navigator.clipboard.readText())).toContain(firstInput.passage);

  await page.getByRole("button", { name: "收藏结果", exact: true }).click();
  await expect(page.getByRole("button", { name: "取消收藏", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "标为已读", exact: true }).click();
  await expect(page.getByRole("button", { name: "标为未读", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "编辑个人备注", exact: true }).click();
  await page.getByLabel("个人备注", { exact: true }).fill("My retained note");
  const metadata = await (await request.get(`${apiBase}/runs/${firstId}/metadata`)).json();
  const concurrent = await request.patch(`${apiBase}/runs/${firstId}/metadata`, { data: { expectedRevision: metadata.revision, note: "Written in another window" } });
  expect(concurrent.ok(), await concurrent.text()).toBe(true);
  await page.getByRole("button", { name: "保存个人备注", exact: true }).click();
  await expect(page.getByText("个人标记已在其他窗口更新", { exact: true })).toBeVisible();
  await expect(page.getByLabel("个人备注", { exact: true })).toHaveValue("My retained note");
  await page.getByRole("button", { name: "读取最新标记", exact: true }).click();
  await page.getByRole("button", { name: "已核对，保留草稿并使用最新版本", exact: true }).click();
  await page.getByRole("button", { name: "保存个人备注", exact: true }).click();
  await expect(page.getByText("My retained note", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText("My retained note", { exact: true })).toBeVisible();
  expect(await (await request.get(`${apiBase}/runs/${firstId}`)).json()).toEqual(firstRun);

  const popupPromise = page.waitForEvent("popup");
  await page.getByRole("link", { name: "打开笔记", exact: true }).click();
  const notePage = await popupPromise;
  await expect(notePage.locator("#noteTitle")).toHaveText(firstInput.caption);
  await expect(notePage.locator("#noteText")).toHaveText(firstInput.passage);
  await notePage.close();

  const secondInput = { caption: `${key} second`, passage: "# Confirmed revision\n\n1. First item\n2. Changed item\n\nAnother retained source." };
  const launched = await request.post(`${apiBase}/workflow-packages/${key}/launches`, { data: { workflowKey: "retain", parameters: secondInput, revisionHash: originalHash, launchId: crypto.randomUUID() } });
  expect(launched.ok(), await launched.text()).toBe(true);
  const secondId = (await launched.json()).id;
  await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${secondId}`)).json()).status, { timeout: 60_000 }).toBe("succeeded");
  await page.goto(`/runs/compare?left=${firstId}&right=${secondId}&leftSection=section:0&rightSection=section:0`);
  await expect(page.getByRole("region", { name: "左侧结果", exact: true })).toContainText("Confirmed original");
  await expect(page.getByRole("region", { name: "右侧结果", exact: true })).toContainText("Confirmed revision");
  await expect(page.getByRole("region", { name: "文本差异", exact: true })).toContainText("右侧新增");
  const visuals = await captureResponsiveEvidence(page, directory, "fixed-comparison", page.getByRole("region", { name: "文本差异", exact: true }), [{ name: "固定两次结果", locator: page.getByRole("button", { name: "固定两次结果", exact: true }) }]);
  await page.reload();
  await expect(page.getByRole("region", { name: "左侧结果", exact: true })).toContainText(firstId);
  await expect(page.getByRole("region", { name: "右侧结果", exact: true })).toContainText(secondId);

  await page.goto(`/runs?q=${encodeURIComponent(key)}&isFavorite=true&isRead=true`);
  const historyRow = page.getByRole("row").filter({ hasText: firstInput.caption });
  await expect(historyRow).toBeVisible();
  await historyRow.getByRole("link").first().click();
  await page.getByRole("link", { name: "全部结果", exact: true }).click();
  await expect(page).toHaveURL(/isFavorite=true/);
  await expect(page).toHaveURL(/isRead=true/);
  await expect(page.getByLabel("搜索全部历史", { exact: true })).toHaveValue(key);
  await page.goto("/attention");
  const update = page.locator("article").filter({ has: page.getByRole("heading", { name: secondInput.caption, exact: true }) });
  await expect(update).toBeVisible();
  await update.getByRole("button", { name: "已查看本次更新", exact: true }).click();
  await expect(update).toHaveCount(0);
  const finalMetadata = await (await request.get(`${apiBase}/runs/${firstId}/metadata`)).json();
  expect(finalMetadata).toMatchObject({ isFavorite: true, isRead: true, note: "My retained note" });
  const evidence = { key, originalHash, firstId, secondId, draftId, submissions, firstRun, finalMetadata, visuals };
  writeFileSync(resolve(directory, "cross-sprint.json"), JSON.stringify(evidence, null, 2));
  await testInfo.attach("cross-sprint.json", { body: JSON.stringify(evidence), contentType: "application/json" });
});
