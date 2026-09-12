import { expect, test } from "@playwright/test";
import { apiBase, packageSource, seed } from "./platform-fixtures";

test("imported workflows retain their contract while named controls and graph explain every dependency", async ({ page, request }, testInfo) => {
  const { key, model } = await seed(request);
  const nextKey = `${key}-editor`;
  await page.goto("/workflow-packages/new");
  await page.getByLabel("选择导入文件").setInputFiles({ name: "workflow.yaml", mimeType: "application/yaml", buffer: Buffer.from(packageSource(nextKey, model)) });
  await page.getByRole("button", { name: "替换当前草稿", exact: true }).click();
  await page.getByLabel("工作流集名称", { exact: true }).fill("Edited with controls");
  await page.getByRole("button", { name: "检查工作流", exact: true }).click();
  await expect(page.getByText("检查通过，可以保存并开始任务", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "步骤关系", exact: true }).click();
  const edges = page.getByRole("list", { name: "步骤之间的关系" });
  await expect(edges.getByText("步骤 1 · Reusable analyst → 步骤 2 · Reusable analyst", { exact: true })).toBeVisible();
  for (const label of ["等待完成", "使用结果", "根据结果判断"]) await expect(edges.getByText(label, { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("definition-graph.png"), fullPage: true, animations: "disabled" });
  await page.getByRole("button", { name: "保存工作流", exact: true }).click();
  await expect(page).toHaveURL(`/workflow-packages/${nextKey}`);
  const persisted = await (await request.get(`${apiBase}/workflow-packages/${nextKey}`)).json();
  expect(persisted.definition.metadata.name).toBe("Edited with controls");
  expect(persisted.definition.workflows.main.nodes.second.dependsOn).toEqual(["first"]);
  expect(persisted.plans.main.edges[0].sources.sort()).toEqual(["condition", "control", "input"]);
});

test("invalid step order is explained at the affected control and never saved", async ({ page, request }) => {
  const { key, pkg } = await seed(request);
  await page.goto(`/workflow-packages/${key}`);
  await page.getByRole("button", { name: "步骤 1 · Reusable analyst", exact: true }).click();
  await page.getByRole("combobox", { name: "交给助手的信息 · 来源", exact: true }).click();
  await page.getByRole("option", { name: "步骤 2 · Reusable analyst的结果", exact: true }).click();
  await page.getByRole("button", { name: "保存工作流", exact: true }).click();
  await expect(page.getByText("还有设置需要调整", { exact: true })).toBeVisible();
  await expect(page.getByText(/这些步骤互相等待/).first()).toBeVisible();
  await page.getByRole("button", { name: "Main workflow · 步骤 1 · Reusable analyst · 输入来源", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "交给助手的信息 · 来源", exact: true })).toBeVisible();
  const persisted = await (await request.get(`${apiBase}/workflow-packages/${key}`)).json();
  expect(persisted.source).toBe(pkg.source);
  expect(persisted.definition).toEqual(pkg.definition);
  expect(persisted.packageHash).toBe(pkg.packageHash);
  expect(persisted.plans).toEqual(pkg.plans);
  await page.getByRole("combobox", { name: "交给助手的信息 · 来源", exact: true }).click();
  await page.getByRole("option", { name: "用户填写的信息", exact: true }).click();
  const [savedResponse] = await Promise.all([
    page.waitForResponse((response) => response.request().method() === "PATCH" && response.url() === `${apiBase}/workflow-packages/${key}`),
    page.getByRole("button", { name: "保存工作流", exact: true }).click(),
  ]);
  expect(savedResponse.status()).toBe(200);
  const saved = await savedResponse.json();
  expect(saved.source).toBe(pkg.source);
  expect(saved.definition).toEqual(pkg.definition);
  expect(saved.packageHash).toBe(pkg.packageHash);
  expect(saved.plans).toEqual(pkg.plans);
  await expect(page.getByText("工作流已保存", { exact: true })).toBeVisible();
});

test("expert starts with ordinary task controls and reads durable results after closing the browser", async ({ page, context, request }, testInfo) => {
  const { key } = await seed(request);
  await page.goto(`/workflow-packages/${key}/run`);
  await page.getByRole("link", { name: "填写Main workflow", exact: true }).click();
  await page.getByLabel("summary", { exact: true }).fill("Launch evidence");
  await page.getByRole("button", { name: "开始任务", exact: true }).click();
  await expect(page).toHaveURL(/\/runs\/[^/?]+/);
  const runId = new URL(page.url()).pathname.split("/").at(-1)!;
  await page.close();
  await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${runId}`)).json()).status, { timeout: 60000 }).toBe("succeeded");
  const inspection = await context.newPage();
  await inspection.goto(`/runs/${runId}`);
  await inspection.getByRole("link", { name: "查看执行过程", exact: true }).click();
  await inspection.getByRole("tab", { name: "执行过程", exact: true }).click();
  await expect(inspection.getByLabel("步骤与服务操作")).toBeVisible();
  await inspection.screenshot({ path: testInfo.outputPath("call-evidence.png"), fullPage: true, animations: "disabled" });
  await inspection.getByRole("tab", { name: "本次设置", exact: true }).click();
  await expect(inspection.getByRole("region", { name: "本次输入", exact: true })).toContainText("Launch evidence");
  const snapshot = (await (await request.get(`${apiBase}/runs/${runId}`)).json()).spec;
  expect(snapshot.parameters).toEqual({ summary: "Launch evidence" });
  expect(JSON.stringify(snapshot)).not.toContain("fake-local-key");
  await expect(inspection.getByText(/Frozen run|resourceBindings|packageHash/)).toHaveCount(0);
  await inspection.getByRole("link", { name: "返回结果", exact: true }).click();
  await inspection.getByRole("button", { name: "再运行一次", exact: true }).click();
  await inspection.getByRole("button", { name: "确认并开始新运行", exact: true }).click();
  await expect(inspection).not.toHaveURL(new RegExp(`${runId}$`));
});
