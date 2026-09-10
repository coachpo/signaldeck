import assert from "node:assert/strict";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium, expect as playwrightExpect } from "@playwright/test";

// Reads this campaign's real runs; this runner never creates model responses or launches runs.
const args = Object.fromEntries(process.argv.slice(2).reduce((pairs, item, index, all) => {
  if (index % 2 === 0) pairs.push([item.replace(/^--/, ""), all[index + 1]]);
  return pairs;
}, []));
for (const key of ["base-url", "api-url", "output", "phase"]) assert(args[key], `Missing --${key}`);
assert(["online", "offline"].includes(args.phase), "phase must be online or offline");
for (const key of ["base-url", "api-url"]) {
  assert(["127.0.0.1", "localhost", "[::1]"].includes(new URL(args[key]).hostname), "Only owned loopback services are supported");
}
const directory = resolve(args.output);
const phase = args.phase;
const expect = playwrightExpect.configure({ timeout: 15_000 });
await mkdir(resolve(directory, "screenshots"), { recursive: true });
const load = async name => JSON.parse(await readFile(resolve(directory, name), "utf8"));
const save = async (name, data) => writeFile(resolve(directory, name), `${JSON.stringify(data, null, 2)}\n`);
const runsFile = await load("runs.json");
const runs = Array.isArray(runsFile) ? runsFile : runsFile.runs;
assert(Array.isArray(runs), "runs.json must contain the current invocation's runs array");
function runId(label) {
  const record = runs.find(item => item.label === label);
  assert(record?.id, `Missing required real run ${label}`);
  return record.id;
}
const ids = {
  main: runId("series-manual"), right: runId("series-rerun"),
  read: runId("read-unknown-fault"), write: runId("write-unknown-fault"),
  scheduled: runId("series-natural-schedule"),
};
const api = path => `${args["api-url"].replace(/\/$/, "")}${path}`;
const ui = path => new URL(path, args["base-url"]).href;
async function get(url) {
  const response = await fetch(url, { signal: AbortSignal.timeout(15_000) });
  assert(response.ok, `Read failed: ${response.status} ${new URL(url).pathname}`);
  return response.json();
}
async function usageFacts(id) {
  const usage = { ...await get(api(`/runs/${id}/usage`)) };
  // The observation timestamp changes on every read; all persisted usage facts remain strict.
  delete usage.asOf;
  return usage;
}
function notesLink(notesPage, id) {
  const query = new URLSearchParams({ noteId: id }).toString();
  return notesPage.locator(`#notes a[href*="${query}"]`);
}
async function snapshot() {
  const entries = await Promise.all(Object.entries(ids).map(async ([label, id]) => [label, {
    id, run: await get(api(`/runs/${id}`)), result: await get(api(`/runs/${id}/result`)),
    usage: await usageFacts(id), metadata: await get(api(`/runs/${id}/metadata`)),
  }]));
  return Object.fromEntries(entries);
}
function markdownSection(result) {
  const index = result.sections?.findIndex(section => section.kind === "markdown" && typeof section.value === "string");
  assert(index >= 0, `Real run ${result.runId} must declare a Markdown section`);
  return { ...result.sections[index], index };
}
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "en-US", timezoneId: "Europe/Helsinki", acceptDownloads: true });
await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: new URL(args["base-url"]).origin });
const page = await context.newPage();
const errors = [];
page.on("pageerror", error => errors.push(error.message));
const observations = { phase, ids, startedAt: new Date().toISOString(), responsive: [], checks: [] };
async function download(name, requireText, currentId) {
  const pending = page.waitForEvent("download");
  const action = page.getByRole("button", { name: "导出 Markdown", exact: true });
  await expect(action).toBeEnabled();
  await action.focus();
  await action.press("Enter");
  const item = await pending;
  assert.equal(await item.failure(), null, "Browser download failed");
  const target = resolve(directory, name);
  await item.saveAs(target);
  const text = await readFile(target, "utf8");
  assert(text.includes(currentId), "Export must retain run identity");
  if (requireText) assert(text.includes(requireText), "Export changed confirmed original content");
  await page.getByRole("button", { name: "复制所选正文", exact: true }).click();
  await expect(page.getByText("所选确认内容已复制。", { exact: true })).toBeVisible();
  assert.equal(await page.evaluate(() => navigator.clipboard.readText()), text, "Clipboard differs from real downloaded Markdown");
  return text;
}
async function responsive(target, name, content, control) {
  for (const width of [375, 768, 1024, 1440]) {
    await target.setViewportSize({ width, height: 900 });
    await expect(content).toBeVisible();
    await content.scrollIntoViewIfNeeded();
    await expect(control).toBeEnabled();
    await control.click({ trial: true });
    await control.focus();
    await expect(control).toBeFocused();
    const bounds = await control.boundingBox();
    assert(bounds && bounds.width > 0 && bounds.height > 0, `${name}/${width}: missing usable control`);
    assert(bounds.x >= -1 && bounds.x + bounds.width <= width + 1, `${name}/${width}: control exceeds viewport`);
    const overflow = await target.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    assert(overflow <= 1, `${name}/${width}: horizontal page overflow ${overflow}`);
    await content.scrollIntoViewIfNeeded();
    await target.screenshot({ path: resolve(directory, `screenshots/${name}-${width}.png`), animations: "disabled", fullPage: true });
    observations.responsive.push({ name, width, overflow, keyboardFocus: true, controlBounds: bounds });
  }
}
async function checkUsage(usage) {
  assert(usage.summary.modelCalls > 0, "Required real model usage missing");
  const region = page.getByRole("region", { name: "本次模型用量", exact: true });
  await expect(region).toBeVisible();
  for (const [label, field] of [["输入 token", "inputTokens"], ["输出 token", "outputTokens"], ["模型逻辑调用", "modelCalls"]]) {
    const displayed = region.locator("dl").first().getByText(label, { exact: true }).locator("..").locator("dd");
    await expect(displayed).toHaveText(usage.summary[field] === null ? "未知" : usage.summary[field].toLocaleString("en-US"));
  }
  const detail = region.getByText("按模型查看用量", { exact: true });
  await detail.focus();
  await detail.press("Enter");
  for (const model of usage.models) await expect(region.getByText(`${model.resourceId} · ${model.modelId} · ${model.apiStyle}`, { exact: true })).toBeVisible();
  observations.checks.push("actual model usage matches the API and keyboard opens model breakdown");
}
async function compare(left, right, leftSection, rightSection) {
  const params = new URLSearchParams({ left, right, leftSection: `section:${leftSection.index}`, rightSection: `section:${rightSection.index}` });
  await page.goto(ui(`/runs/compare?${params}`));
  const leftRegion = page.getByRole("region", { name: "左侧结果", exact: true });
  const rightRegion = page.getByRole("region", { name: "右侧结果", exact: true });
  await expect(leftRegion).toContainText(left);
  await expect(rightRegion).toContainText(right);
  await expect(leftRegion.locator(".markdown-preview")).toBeVisible();
  await expect(rightRegion.locator(".markdown-preview")).toBeVisible();
  const diff = page.getByRole("region", { name: "文本差异", exact: true });
  await expect(diff.locator("pre").first()).toBeVisible();
  const firstDiff = await diff.innerText();
  await page.reload();
  await expect.poll(() => diff.innerText()).toBe(firstDiff);
  return { diff, firstDiff, url: page.url() };
}
async function faults(before, prepare) {
  for (const label of ["read", "write"]) {
    const item = before[label];
    const readOnly = label === "read";
    assert.equal(item.run.hasUnknownEffects, !readOnly);
    assert.equal(item.run.hasUnknownResults, readOnly);
    assert(readOnly ? item.result.readUnknownEvidenceIds.length > 0 : item.result.unknownEvidenceIds.length > 0);
    await page.goto(ui(`/runs/${item.id}`));
    await expect(page.getByText(readOnly ? "读取结果未确认" : "保存状态待核实", { exact: true })).toBeVisible();
    if (readOnly) await expect(page.getByText("保存状态待核实", { exact: true })).toHaveCount(0);
    if (prepare) {
      await page.getByRole("button", { name: "再运行一次", exact: true }).click();
      const confirm = page.getByRole("button", { name: "确认并开始新运行", exact: true });
      const guard = page.getByLabel("我已核实目标位置与执行证据，确认需要再次执行");
      if (readOnly) { await expect(confirm).toBeEnabled(); await expect(guard).toHaveCount(0); }
      else { await expect(confirm).toBeDisabled(); await expect(guard).not.toBeChecked(); }
    }
    await page.screenshot({ path: resolve(directory, `screenshots/${phase}-${label}-unknown.png`), fullPage: true });
    // A failed operation need not have exportable content; only export confirmed sections when present.
    if (item.result.sections?.length || item.result.body !== null || item.result.receipt !== null) {
      const exported = await download(`${phase}-${label}-unknown.md`, null, item.id);
      assert(exported.includes(readOnly ? "读取结果未确认" : "保存状态待核实"));
      if (readOnly) assert(!exported.includes("保存状态待核实"));
    } else await expect(page.getByRole("button", { name: "导出 Markdown", exact: true })).toBeDisabled();
    await page.goto(ui(`/runs/compare?left=${ids.main}&right=${item.id}`));
    const compared = page.getByRole("region", { name: "右侧结果", exact: true });
    await expect(compared).toContainText(readOnly ? "读取结果未确认" : "保存状态待核实");
    if (readOnly) await expect(compared).not.toContainText("保存状态待核实");
    await page.goto(ui(`/runs?q=${encodeURIComponent(item.id)}`));
    const row = page.getByRole("row").filter({ has: page.locator(`a[href*="/runs/${item.id}"]`) });
    await expect(row).toContainText(readOnly ? "读取结果未确认" : "保存状态待核实");
    if (readOnly) await expect(row).not.toContainText("保存状态待核实");
  }
  await page.goto(ui("/attention?view=all"));
  for (const label of ["read", "write"]) {
    const article = page.locator("article").filter({ has: page.locator(`a[href="/runs/${ids[label]}"]`) });
    await expect(article).toContainText(label === "read" ? "读取结果未确认" : "保存状态待核实");
    if (label === "read") await expect(article).not.toContainText("保存状态待核实");
  }
  observations.checks.push("read/write uncertainty is consistent in result, history, attention, comparison and available exports");
}
try {
  const before = await snapshot();
  const main = markdownSection(before.main.result), right = markdownSection(before.right.result);
  assert.equal(before.main.run.status, "succeeded");
  assert.equal(before.right.run.status, "succeeded");
  if (phase === "online") {
    await page.goto(ui(`/runs/${ids.main}`));
    const body = page.getByRole("region", { name: main.label, exact: true });
    await expect(body).toBeVisible();
    assert(/^\s*\d+[.)]\s+/m.test(main.value), "Real Markdown lacks the requested ordered list");
    assert(/^\s*[-*+]\s+/m.test(main.value), "Real Markdown lacks the requested unordered list");
    await expect(body.locator("ol").first()).toHaveCSS("list-style-type", "decimal");
    await expect(body.locator("ul").first()).toHaveCSS("list-style-type", "disc");
    for (const list of [body.locator("ol li").first(), body.locator("ul li").first()]) {
      await expect(list).toBeVisible();
      assert((await list.innerText()).trim().length > 0, "List item is empty");
    }
    await checkUsage(before.main.usage);
    const exported = await download("export.md", main.value, ids.main);
    observations.exportCharacters = exported.length;
    await responsive(page, "result", body, page.getByRole("button", { name: "复制所选正文", exact: true }));
    if (!before.main.metadata.isFavorite) await page.getByRole("button", { name: "收藏结果", exact: true }).click();
    await expect(page.getByRole("button", { name: "取消收藏", exact: true })).toBeVisible();
    if (!before.main.metadata.isRead) await page.getByRole("button", { name: "标为已读", exact: true }).click();
    await expect(page.getByRole("button", { name: "标为未读", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "编辑个人备注", exact: true }).click();
    const note = `Verified in owned campaign: ${ids.main}`;
    await page.getByLabel("个人备注", { exact: true }).fill(note);
    await page.getByRole("button", { name: "保存个人备注", exact: true }).click();
    await expect(page.getByText(note, { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText(note, { exact: true })).toBeVisible();
    assert.deepEqual(await get(api(`/runs/${ids.main}`)), before.main.run, "Metadata modified immutable Run");
    assert.deepEqual(await get(api(`/runs/${ids.main}/result`)), before.main.result, "Metadata modified confirmed output");
    const link = page.getByRole("link", { name: "打开笔记", exact: true });
    await expect(link).toBeVisible();
    const notesHref = await link.getAttribute("href");
    assert(notesHref && ["127.0.0.1", "localhost"].includes(new URL(notesHref).hostname), "Notes link must target owned plugin");
    const popup = page.waitForEvent("popup");
    await link.click();
    const notesPage = await popup;
    const sources = await load("source-sets.json");
    const sourceRun = sources.runs.find(item => item.runId === ids.main);
    assert(sourceRun?.savedNoteId, "Missing current real run's saved Notes identity");
    const notesOrigin = new URL(notesHref).origin;
    const stored = await get(`${notesOrigin}/api/note?id=${encodeURIComponent(sourceRun.savedNoteId)}`);
    await expect(notesPage.locator("#noteTitle")).toHaveText(stored.title);
    await expect(notesPage.locator("#noteText")).toHaveText(stored.text);
    await expect(notesPage.locator("#noteSourceKind")).toHaveText("派生笔记");
    assert.equal(stored.text, main.value, "Notes public page does not retain confirmed Markdown");
    assert.deepEqual([...stored.sourceNoteIds].sort(), [...sourceRun.savedSourceNoteIds].sort());
    for (const id of stored.sourceNoteIds) await expect(notesPage.locator("#noteSources a").filter({ hasText: id })).toBeVisible();
    await notesPage.locator("#back").focus();
    await notesPage.locator("#back").press("Enter");
    await expect(notesPage.locator("#collection")).toBeVisible();
    await notesPage.locator("#collection").selectOption(stored.collection);
    await notesPage.locator("#includeDerived").selectOption("false");
    await notesPage.getByRole("button", { name: "搜索", exact: true }).click();
    await expect(notesPage.locator("#status")).toHaveText("");
    await expect(notesLink(notesPage, stored.id)).toHaveCount(0);
    const original = await get(`${notesOrigin}/api/notes?${new URLSearchParams({ collection: stored.collection, includeDerived: "false", limit: "50" })}`);
    assert(original.notes.every(item => item.sourceKind !== "derived"));
    for (const item of original.notes.slice(0, 20)) await expect(notesLink(notesPage, item.id)).toBeVisible();
    await notesPage.locator("#includeDerived").selectOption("true");
    await notesPage.getByRole("button", { name: "搜索", exact: true }).click();
    await expect(notesLink(notesPage, stored.id)).toBeVisible();
    await responsive(notesPage, "notes", notesPage.getByRole("region", { name: "浏览笔记", exact: true }), notesPage.getByRole("button", { name: "搜索", exact: true }));
    observations.notes = { url: notesHref, stored, originalNoteIds: original.notes.map(item => item.id), filters: ["false", "true"] };
    await notesPage.close();
    const comparison = await compare(ids.main, ids.right, main, right);
    observations.comparison = { url: comparison.url, text: comparison.firstDiff };
    await responsive(page, "comparison", comparison.diff, page.getByRole("button", { name: "固定两次结果", exact: true }));
    await faults(before, true);
    const closed = await load("schedule-browser.json");
    assert(closed.browserClosed, "The schedule browser was not closed before firing");
    await page.goto(ui(`/runs/${ids.scheduled}`));
    await expect(page.getByRole("heading", { name: before.scheduled.result.title, exact: true })).toBeVisible();
    await page.goto(ui("/attention?view=all"));
    const scheduledUpdate = page.locator("article").filter({ has: page.locator(`a[href="/runs/${ids.scheduled}"]`) });
    await expect(scheduledUpdate).toBeVisible();
    await scheduledUpdate.getByRole("button", { name: "已查看本次更新", exact: true }).click();
    await expect(scheduledUpdate.getByRole("button", { name: "将本次更新标为未查看", exact: true })).toBeEnabled();
    const updates = await get(api("/attention?view=all"));
    assert(updates.items.find(item => item.runId === ids.scheduled)?.isRead, "Scheduled update was not marked read");
    assert.deepEqual(await get(api(`/runs/${ids.scheduled}`)), before.scheduled.run, "Viewing schedule result changed its Run");
    observations.scheduleBrowser = closed;
    observations.checks.push("opened the saved schedule, closed that browser before natural firing, then reopened and processed its result");
    await save("browser-online-snapshot.json", await snapshot());
  } else {
    const previous = await load("browser-online-snapshot.json");
    assert.deepEqual(before, previous, "Offline API changed confirmed Run, result, usage or personal metadata");
    const online = await load("browser-online.json");
    const notesHealth = await fetch(`${new URL(online.notes.url).origin}/health`, { signal: AbortSignal.timeout(2000) }).then(response => response.status).catch(() => null);
    assert.equal(notesHealth, null, "Notes must actually be stopped before offline acceptance");
    await page.goto(ui(`/runs/${ids.main}`));
    await expect(page.getByRole("region", { name: main.label, exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: "取消收藏", exact: true })).toBeVisible();
    await expect(page.getByText(previous.main.metadata.note, { exact: true })).toBeVisible();
    await checkUsage(before.main.usage);
    const exported = await download("offline.md", main.value, ids.main);
    assert.equal(exported, await readFile(resolve(directory, "export.md"), "utf8"), "Offline export changed content");
    const comparison = await compare(ids.main, ids.right, main, right);
    assert.equal(comparison.firstDiff, online.comparison.text, "Offline fixed comparison changed");
    await faults(before, false);
    assert.deepEqual(await snapshot(), previous, "Offline browser reading mutated frozen facts");
    observations.notesConnectionRefused = true;
    observations.checks.push("Core history, export, clipboard, model usage, metadata and comparison survive actual Notes shutdown");
    await save("offline.json", observations);
  }
  assert.deepEqual(errors, [], "Browser runtime errors");
  observations.completedAt = new Date().toISOString();
  await save(`browser-${phase}.json`, observations);
} catch (error) {
  observations.failure = { name: error.name, message: error.message, stack: error.stack };
  await page.screenshot({ path: resolve(directory, `screenshots/${phase}-failure.png`), fullPage: true }).catch(() => {});
  await save(`browser-${phase}-failure.json`, observations);
  throw error;
} finally {
  await context.close();
  await browser.close();
}
