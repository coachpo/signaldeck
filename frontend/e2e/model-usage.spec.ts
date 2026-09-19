import { mkdir, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { apiBase, seed } from "./platform-fixtures";
import { captureResponsiveEvidence } from "./responsive-evidence";

test.use({ timezoneId: "Europe/Helsinki" });

test("optional output budget survives editing and model usage is readable", async ({ page, request }) => {
  test.setTimeout(180_000);
  const { key } = await seed(request);
  const launch = async (launchId: string) => {
    const response = await request.post(`${apiBase}/workflow-packages/${key}/launches`, {
      data: { workflowKey: "main", parameters: { summary: "Usage evidence" }, launchId },
    });
    expect(response.ok(), await response.text()).toBeTruthy();
    return (await response.json()).id as string;
  };
  const oldRunId = await launch(`${key}-old`);
  await page.goto(`/workflow-packages/${key}`);
  await page.getByRole("tab", { name: "制作内容", exact: true }).click();
  await page.getByRole("button", { name: "Reusable analyst", exact: true }).click();
  await page.getByRole("combobox", { name: "单次输出方式", exact: true }).click();
  await page.getByRole("option", { name: "指定额度", exact: true }).click();
  const outputLimit = page.getByLabel("单次输出数值", { exact: true });
  await outputLimit.fill("128");
  const mode = page.getByRole("switch", { name: "专家模式", exact: true });
  await mode.check();
  await mode.uncheck();
  await mode.check();
  await expect(outputLimit).toHaveValue("128");
  const [saved] = await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url() === `${apiBase}/workflow-packages/${encodeURIComponent(key)}` &&
        response.request().method() === "PATCH",
      { timeout: 15_000 },
    ),
    page.getByRole("button", { name: "保存工作流", exact: true }).click(),
  ]);
  expect(saved.status(), await saved.text()).toBe(200);
  expect((await saved.json()).definition.agents.analyst.budget.maxOutputTokens).toBe(128);
  const preparation = await request.post(`${apiBase}/workflow-packages/${key}/prepare`, {
    data: { workflowKey: "main", parameters: { summary: "Usage evidence" } },
  });
  expect(preparation.status(), await preparation.text()).toBe(200);
  expect((await preparation.json()).effectiveSettings.agents.analyst.budget.maxOutputTokens).toBe(128);
  const runId = await launch(`${key}-limited`);
  await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${runId}`)).json()).status, { timeout: 90_000 }).toBe("succeeded");
  const detail = await (await request.get(`${apiBase}/runs/${runId}`)).json();
  const original = await (await request.get(`${apiBase}/runs/${oldRunId}`)).json();
  expect(original.spec.definition.agents.analyst.budget).not.toHaveProperty("maxOutputTokens");
  expect(detail.spec.definition.agents.analyst.budget.maxOutputTokens).toBe(128);
  const usage = await (await request.get(`${apiBase}/runs/${runId}/usage`)).json();
  expect(usage.summary).toMatchObject({ modelCalls: 2, confirmedCalls: 2, inputTokens: 6, outputTokens: 4, usageCoverage: "complete", networkAttempts: 2 });
  await page.goto(`/runs/${runId}`);
  const section = page.getByRole("region", { name: "本次模型用量", exact: true });
  await expect(section).toBeVisible();
  await expect(section.locator("dl").first().getByText("输入用量", { exact: true }).locator("..").locator("dd")).toHaveText(String(usage.summary.inputTokens));
  await expect(section.locator("dl").first().getByText("输出用量", { exact: true }).locator("..").locator("dd")).toHaveText(String(usage.summary.outputTokens));
  const breakdown = section.getByText("按模型查看用量", { exact: true });
  await breakdown.focus();
  await breakdown.press("Enter");
  await expect(section.getByText(/fake-e2e-model/)).toBeVisible();
  const directory = resolve("../output/playwright/model-usage");
  await mkdir(directory, { recursive: true });
  const visuals = await captureResponsiveEvidence(page, directory, "model-usage", section, [{ name: "model breakdown", locator: breakdown }]);
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: /今日模型用量.*Europe\/Helsinki/ })).toBeVisible();
  await writeFile(resolve(directory, "verification.json"), JSON.stringify({ key, oldRunId, runId, usage, visuals }, null, 2));
});

test("generic task budgets survive draft restore and freeze independently of the package", async ({ page, request }) => {
  test.setTimeout(180_000);
  page.setDefaultTimeout(15_000);
  const { key, pkg } = await seed(request);
  await page.goto(`/tasks/new?packageKey=${key}&workflowKey=main`);
  await page.getByLabel("summary", { exact: true }).fill("Independent budget evidence");
  await page.getByText(/^用量与时间限制 ·/).click();
  await page.getByRole("combobox", { name: "累计模型用量方式", exact: true }).click();
  await page.getByRole("option", { name: "不设限", exact: true }).click();
  await page.getByRole("combobox", { name: "单次输出方式", exact: true }).click();
  await page.getByRole("option", { name: "由模型服务决定", exact: true }).click();
  const preparation = page.getByRole("region", { name: "本次有效设置", exact: true });
  await expect(preparation.getByText("由模型服务决定", { exact: false })).toBeVisible();
  await page.getByLabel("草稿名称", { exact: true }).fill("Budget draft");
  await page.getByRole("button", { name: "保存草稿", exact: true }).click();
  await expect(page).toHaveURL(/draftId=/);
  await page.reload();
  await page.getByText(/^用量与时间限制 ·/).click();
  await expect(page.getByRole("combobox", { name: "累计模型用量方式", exact: true })).toHaveText("不设限");
  await expect(page.getByRole("combobox", { name: "单次输出方式", exact: true })).toHaveText("由模型服务决定");
  await expect(preparation.getByText("由模型服务决定", { exact: false })).toBeVisible();
  const directory = resolve("../output/playwright/generic-budgets");
  await mkdir(directory, { recursive: true });
  await captureResponsiveEvidence(page, directory, "budget-controls", page.getByRole("combobox", { name: "单次输出方式", exact: true }), [
    { name: "start task", locator: page.getByRole("button", { name: "开始任务", exact: true }) },
  ]);
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/[^/?]+/);
  const runId = new URL(page.url()).pathname.split("/").at(-1)!;
  await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${runId}`)).json()).status, { timeout: 90_000 }).toBe("succeeded");
  const detail = await (await request.get(`${apiBase}/runs/${runId}`)).json();
  expect(detail.spec.packageHash).toBe(pkg.packageHash);
  expect(detail.spec.definition).toEqual(pkg.definition);
  expect(detail.spec.executionOptions.agentBudgets.analyst).toEqual({ maxTokens: "unlimited", maxOutputTokens: "provider_default" });
  expect(detail.spec.effectiveAgentBudgets.analyst).toMatchObject({ maxTokens: "unlimited", maxOutputTokens: "provider_default" });
  await expect(page.getByText("本次冻结的用量与时间限制", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: "修改输入后开始", exact: true }).click();
  await page.getByText(/^用量与时间限制 ·/).click();
  await expect(page.getByRole("combobox", { name: "单次输出方式", exact: true })).toHaveText("由模型服务决定");
  await page.getByRole("combobox", { name: "累计模型用量方式", exact: true }).click();
  await page.getByRole("option", { name: "指定额度", exact: true }).click();
  await page.getByLabel("累计模型用量数值", { exact: true }).fill("1");
  await expect(preparation.getByText("配置已就绪", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: /开始任务|确认变化并开始/, exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/[^/?]+/);
  const failedRunId = new URL(page.url()).pathname.split("/").at(-1)!;
  await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${failedRunId}`)).json()).status, { timeout: 90_000 }).toBe("failed");
  const recovery = page.getByRole("link", { name: "调整后重新运行", exact: true });
  await expect(recovery).toBeVisible();
  await recovery.click();
  await page.getByText(/^用量与时间限制 ·/).click();
  await expect(page.getByLabel("累计模型用量数值", { exact: true })).toHaveValue("1");
});
