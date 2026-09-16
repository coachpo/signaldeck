import { expect, test, type Locator } from "@playwright/test";
import { parse, stringify } from "yaml";
import { apiBase, seed } from "./platform-fixtures";

async function expectReachable(action: Locator) {
  await expect(action).toBeInViewport({ timeout: 100 });
  const overflow = await action.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const region = element.closest('section[aria-label="结果内容"]')!;
    const bounds = region.getBoundingClientRect();
    const top = Math.max(0, bounds.top + region.clientTop);
    const left = Math.max(0, bounds.left + region.clientLeft);
    return Math.max(top - rect.top, left - rect.left,
      rect.bottom - Math.min(innerHeight, bounds.top + region.clientTop + region.clientHeight),
      rect.right - Math.min(innerWidth, bounds.left + region.clientLeft + region.clientWidth));
  });
  // CSS bounds can be fractional while the native scroll extent is rounded.
  expect(overflow).toBeLessThanOrEqual(1);
}

test("long results remain readable by wheel and keyboard with reachable evidence actions", async ({ page, request }, testInfo) => {
  test.setTimeout(180_000);
  const { key, source } = await seed(request);
  const definition = parse(source);
  definition.workflows.main.outputMapping = { ref: "workflow.input" };
  definition.workflows.main.presentation = {
    version: "signaldeck.presentation/1",
    sections: [{ kind: "markdown", ref: "workflow.output.summary", label: "阅读回归正文", required: true }],
  };
  const saved = await request.patch(`${apiBase}/workflow-packages/${key}`, {
    data: { manifestSource: stringify(definition, { aliasDuplicateObjects: false }) },
  });
  expect(saved.ok(), await saved.text()).toBe(true);
  const parameters = { summary: Array.from({ length: 70 }, (_, i) => `第 ${i + 1} 段：这是一段需要连续滚动阅读的已确认内容。`).join("\n\n") + "\n\n正文末段：完整阅读确认。" };
  const prepared = await request.post(`${apiBase}/workflow-packages/${key}/prepare`, { data: { workflowKey: "main", parameters } });
  expect(prepared.ok(), await prepared.text()).toBe(true);
  const preparation = await prepared.json();
  expect(preparation.ready).toBe(true);
  const launched = await request.post(`${apiBase}/workflow-packages/${key}/launches`, {
    data: { workflowKey: "main", parameters, launchId: crypto.randomUUID(), bindingToken: preparation.bindingToken },
  });
  expect(launched.ok(), await launched.text()).toBe(true);
  const run = await launched.json();
  await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${run.id}`)).json()).status, { timeout: 60_000 }).toBe("succeeded");

  for (const viewport of [{ width: 1440, height: 900 }, { width: 1280, height: 720 }, { width: 375, height: 900 }, { width: 768, height: 900 }, { width: 1024, height: 900 }]) {
    await page.setViewportSize(viewport);
    await page.goto(`/runs?q=${key}&status=succeeded`);
    const historyUrl = page.url();
    await page.getByRole("link", { name: "Main workflow", exact: true }).click();
    const content = page.getByRole("region", { name: "结果内容", exact: true });
    const lastParagraph = page.getByText("正文末段：完整阅读确认。", { exact: true });
    const evidence = page.getByRole("link", { name: "查看执行过程", exact: true });
    await expect(lastParagraph).not.toBeInViewport();
    const bounds = await content.boundingBox();
    expect(bounds).not.toBeNull();
    await page.mouse.move(bounds!.x + bounds!.width / 2, bounds!.y + bounds!.height / 2);
    // Only real wheel input advances the page; locator clicks must not rescue scrolling.
    await expect(async () => {
      await page.mouse.wheel(0, Math.min(300, bounds!.height / 2));
      await expect(lastParagraph).toBeInViewport({ timeout: 100 });
    }).toPass({ timeout: 15_000, intervals: [100] });
    await expect(async () => {
      await page.mouse.wheel(0, 600);
      await expectReachable(evidence);
    }).toPass({ timeout: 10_000, intervals: [100] });
    await content.focus();
    await page.keyboard.press("Home");
    await expect.poll(() => content.evaluate(element => element.scrollTop)).toBe(0);
    await page.keyboard.press("PageDown");
    await expect.poll(() => content.evaluate(element => element.scrollTop)).toBeGreaterThan(0);
    await page.keyboard.press("End");
    await expect(async () => expectReachable(evidence)).toPass();
    await page.screenshot({ path: testInfo.outputPath(`result-bottom-${viewport.width}.png`) });
    await evidence.click();
    await page.getByRole("link", { name: "返回结果", exact: true }).click();
    await page.getByRole("link", { name: "全部结果", exact: true }).click();
    await expect(page).toHaveURL(historyUrl);
  }
});
