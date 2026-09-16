import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { connectTaskServices } from "./task-fixtures";
import { apiBase, seed } from "./platform-fixtures";

test.skip(process.env.SIGNALDECK_E2E_INTEGRATED !== "1", "Requires the owned integrated plugin harness");
test.describe.configure({ mode: "default" });

type PluginPage = { mountKey: string; pluginId: string; title: string; pageUrl: string; enabled: boolean };
let pages: PluginPage[];

test.beforeAll(async ({ request }) => {
  const absent = await request.get(`${apiBase}/plugin-pages`);
  expect(absent.ok()).toBe(true);
  expect(Array.isArray(await absent.json())).toBe(true);
  for (const [kind, fallback] of [["NOTES", "18082"], ["FINANCE", "18083"], ["GENERIC", "18085"]]) {
    const release = await request.get(`http://127.0.0.1:${process.env[`SIGNALDECK_E2E_${kind}_PORT`] ?? fallback}/release`);
    expect(release.ok(), await release.text()).toBe(true);
    const installed = await request.post(`${apiBase}/plugins`, { data: { release: await release.json(), enabled: true } });
    expect(installed.ok(), await installed.text()).toBe(true);
  }
  pages = await (await request.get(`${apiBase}/plugin-pages`)).json();
  expect(pages).toHaveLength(3);
});

function plugin(id: string) { return pages.find(item => item.pluginId === id)!; }

test("real Finance draft and Core task draft survive cross-workspace navigation", async ({ page, request }) => {
  const finance = plugin("signaldeck/finance");
  const notes = plugin("example/notes");
  const { key } = await seed(request);
  await page.goto(`/workflow-packages/${key}`);
  await page.getByRole("button", { name: "Reusable analyst", exact: true }).click();
  const instructions = "Retain this task draft across independent workspaces.";
  await page.getByLabel("助手任务说明", { exact: true }).fill(instructions);
  await page.getByTestId(`nav-plugin-${finance.mountKey}`).click();
  await page.getByRole("button", { name: "保留草稿并离开", exact: true }).click();
  const frame = page.frameLocator(`iframe[title="${finance.title}"]`);
  await expect(frame.getByRole("heading", { name: "报告", exact: true })).toBeVisible();
  await page.getByRole("switch", { name: "专家模式", exact: true }).check();
  await frame.getByRole("button", { name: "新建报告", exact: true }).click();
  await frame.getByLabel("名称", { exact: true }).fill("Unfinished integrated report");
  await frame.getByRole("textbox", { name: "报告正文", exact: true }).fill("Keep the entire unsaved business draft.");
  await page.getByTestId(`nav-plugin-${notes.mountKey}`).click();
  await expect(page.frameLocator(`iframe[title="${notes.title}"]`).getByRole("heading", { name: "资料", exact: true })).toBeVisible();
  await page.goBack();
  await expect(frame.getByLabel("名称", { exact: true })).toHaveValue("Unfinished integrated report");
  await expect(frame.getByRole("textbox", { name: "报告正文", exact: true })).toHaveValue("Keep the entire unsaved business draft.");
  await frame.getByRole("button", { name: "保存", exact: true }).click();
  await expect(frame.getByRole("status")).toContainText("已保存");
  await page.goBack();
  await expect(page.getByLabel("助手任务说明", { exact: true })).toHaveValue(instructions);
});

test("ordinary task inputs survive navigation into and out of a plugin", async ({ page }) => {
  await page.goto("/tasks/new?packageKey=research_notes&workflowKey=capture");
  await page.getByLabel("标题", { exact: true }).fill("Unfinished ordinary task");
  await page.getByLabel("原文", { exact: true }).fill("Keep original business input in memory.");
  await page.getByTestId(`nav-plugin-${plugin("example/notes").mountKey}`).click();
  await expect(page.frameLocator(`iframe[title="${plugin("example/notes").title}"]`).getByRole("heading", { name: "资料", exact: true })).toBeVisible();
  await page.goBack();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue("Unfinished ordinary task");
  await expect(page.getByLabel("原文", { exact: true })).toHaveValue("Keep original business input in memory.");
});

test("Finance format drafts and filled template inputs survive sidebar roundtrips", async ({ page, request }) => {
  const finance = plugin("signaldeck/finance");
  const notes = plugin("example/notes");
  const financeApi = `http://127.0.0.1:${process.env.SIGNALDECK_E2E_FINANCE_PORT ?? "18083"}/api`;
  const name = `Sidebar format ${crypto.randomUUID()}`;
  const content = "<!-- input: company | 公司名称 | required -->\n# {{inputs.company}}\nSaved original format.";
  const created = await request.post(`${financeApi}/templates`, { data: { name, content } });
  expect(created.ok(), await created.text()).toBe(true);
  const template = await created.json();
  const writes: string[] = [];
  page.on("request", outgoing => {
    if (outgoing.url().includes(`/_plugins/${finance.mountKey}/api/`) && !["GET", "HEAD"].includes(outgoing.method())) writes.push(`${outgoing.method()} ${outgoing.url()}`);
  });
  await page.goto(finance.pageUrl);
  const frame = page.frameLocator(`iframe[title="${finance.title}"]`);
  await frame.getByRole("button", { name: "使用已有格式", exact: true }).click();
  await frame.getByRole("button", { name: new RegExp(name) }).click();
  await frame.getByLabel("公司名称（必填）", { exact: true }).fill("Preserved business input");
  await page.getByTestId(`nav-plugin-${notes.mountKey}`).click();
  await expect(page.frameLocator(`iframe[title="${notes.title}"]`).getByRole("heading", { name: "资料", exact: true })).toBeVisible();
  await page.getByTestId(`nav-plugin-${finance.mountKey}`).click();
  await expect(frame.getByLabel("公司名称（必填）", { exact: true })).toHaveValue("Preserved business input");
  await page.getByRole("switch", { name: "专家模式", exact: true }).check();
  const draft = "# ⟦公司名称⟧\nUnsaved format wording survives sidebar navigation.";
  await frame.getByRole("textbox", { name: "报告正文", exact: true }).fill(draft);
  await page.getByTestId(`nav-plugin-${notes.mountKey}`).click();
  await expect(page.frameLocator(`iframe[title="${notes.title}"]`).getByRole("heading", { name: "资料", exact: true })).toBeVisible();
  await page.getByTestId(`nav-plugin-${finance.mountKey}`).click();
  await expect(frame.getByRole("textbox", { name: "报告正文", exact: true })).toHaveValue(draft);
  await page.getByRole("switch", { name: "专家模式", exact: true }).uncheck();
  await expect(frame.getByLabel("公司名称（必填）", { exact: true })).toHaveValue("Preserved business input");
  expect(writes).toEqual([]);
  const saved = await (await request.get(`${financeApi}/templates/${template.id}`)).json();
  expect(saved.content).toBe(content);
});

test("Finance deep links refresh, all three plugin pages fit four widths inside one shell", async ({ page, request }, testInfo) => {
  const finance = plugin("signaldeck/finance");
  const created = await request.post(`http://127.0.0.1:${process.env.SIGNALDECK_E2E_FINANCE_PORT ?? "18083"}/api/reports`, {
    data: { name: `Integrated deep link ${crypto.randomUUID()}`, content: "# Saved report\n\nReal Finance storage." },
  });
  expect(created.ok(), await created.text()).toBe(true);
  const report = await created.json();
  await page.goto(`${finance.pageUrl}?report=${encodeURIComponent(report.slug)}`);
  const financeFrame = page.frameLocator(`iframe[title="${finance.title}"]`);
  await expect(financeFrame.getByRole("heading", { name: report.name, exact: true })).toBeVisible();
  await page.reload();
  await expect(financeFrame.getByRole("heading", { name: report.name, exact: true })).toBeVisible();
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    for (const entry of pages) {
      await page.goto(entry.pageUrl);
      const frame = page.frameLocator(`iframe[title="${entry.title}"]`);
      await expect(frame.getByRole("heading", { name: entry.title, exact: true })).toBeVisible();
      await expect(page.getByRole("main")).toHaveCount(1);
      await expect(frame.getByRole("switch", { name: "专家模式", exact: true })).toHaveCount(0);
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(1);
      expect(await frame.locator("html").evaluate(element => element.scrollWidth - element.clientWidth)).toBeLessThanOrEqual(1);
      const directory = resolve("../output/playwright/integrated-plugins");
      mkdirSync(directory, { recursive: true });
      const screenshot = resolve(directory, `${entry.title}-${width}.png`);
      await page.screenshot({ path: screenshot, fullPage: true });
      await testInfo.attach(`${entry.title}-${width}`, { path: screenshot, contentType: "image/png" });
    }
  }
});

test("a confirmed Notes result opens its workspace and retains its source navigation", async ({ page, request }, testInfo) => {
  test.setTimeout(150_000);
  await page.addInitScript(() => {
    const messages: unknown[] = [];
    Object.assign(window, { integratedBridgeMessages: messages });
    window.addEventListener("message", event => {
      if (event.data?.protocol === "signaldeck.pluginUi/1") messages.push({ origin: event.origin, ...event.data });
    });
  });
  await connectTaskServices(request, false);
  await page.goto("/tasks/new?packageKey=research_notes&workflowKey=capture");
  const title = `Integrated original ${crypto.randomUUID()}`;
  await page.getByLabel("标题", { exact: true }).fill(title);
  await page.getByLabel("原文", { exact: true }).fill("Original evidence from the real durable Notes operation.");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/[^/]+$/);
  const resultUrl = page.url();
  const runId = new URL(resultUrl).pathname.split("/").at(-1)!;
  await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${runId}`)).json()).status, { timeout: 90_000 }).toBe("succeeded");
  await page.reload();
  await page.getByRole("link", { name: "打开笔记", exact: true }).click();
  const notes = plugin("example/notes");
  await expect(page).toHaveURL(new RegExp(`/apps/${notes.mountKey}/.*noteId=`));
  const frame = page.frameLocator(`iframe[title="${notes.title}"]`);
  const noteUrl = page.url();
  await expect(frame.getByRole("heading", { name: title, exact: true })).toBeVisible();
  await page.goBack();
  await expect(page).toHaveURL(resultUrl);
  await page.goForward();
  try {
    await expect(page).toHaveURL(noteUrl);
    await expect(frame.getByRole("heading", { name: title, exact: true })).toBeVisible();
  } catch (error) {
    await testInfo.attach("forward-navigation-state", { body: JSON.stringify({ url: page.url(), frames: await Promise.all(page.frames().map(async entry => ({ url: entry.url(), text: await entry.locator("body").innerText(), messages: await entry.evaluate(() => Reflect.get(window, "integratedBridgeMessages")) }))) }), contentType: "application/json" });
    throw error;
  }
  await testInfo.attach("forward-bridge-messages", { body: JSON.stringify(await page.evaluate(() => Reflect.get(window, "integratedBridgeMessages"))), contentType: "application/json" });
  await page.reload();
  await expect(frame.getByRole("heading", { name: title, exact: true })).toBeVisible();
  await page.getByRole("link", { name: "返回来源结果", exact: true }).click();
  await expect(page).toHaveURL(resultUrl);
});

test("a generic plugin receives a non-query deep link without core business routing", async ({ page }) => {
  const generic = plugin("example/field-journal");
  await page.goto(`${generic.pageUrl}detail`);
  const frame = page.frameLocator(`iframe[title="${generic.title}"]`);
  await expect(frame.getByRole("heading", { name: "观察详情", exact: true })).toBeVisible();
  await page.reload();
  await expect(frame.getByRole("heading", { name: "观察详情", exact: true })).toBeVisible();
});

test("disabled releases retain historical pages while absent mounts never load", async ({ page, request }) => {
  const generic = plugin("example/field-journal");
  const disabled = await request.patch(`${apiBase}/plugins/${generic.pluginId}`, { data: { enabled: false } });
  expect(disabled.ok(), await disabled.text()).toBe(true);
  await page.goto(generic.pageUrl);
  await expect(page.frameLocator(`iframe[title="${generic.title}"]`).getByRole("heading", { name: "观察记录", exact: true })).toBeVisible();
  await expect(page.getByTestId(`nav-plugin-${generic.mountKey}`)).toHaveCount(0);
  await page.goto("/apps/not-installed/");
  await expect(page.locator("iframe")).toHaveCount(0);
  await expect(page.getByRole("main")).toBeVisible();
});
