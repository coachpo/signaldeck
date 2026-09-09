import { expect, test, type APIRequestContext } from "@playwright/test";
import { stringify } from "yaml";
import { apiBase, seed } from "./platform-fixtures";

function source(key: string, model: string, renamed: boolean) {
  const field = renamed ? "manuscript" : "includeRisk";
  const output = renamed ? "folio" : "reportId";
  const group = renamed ? "shelf" : "collection";
  const inputSchema = {
    type: "object",
    properties: {
      [field]: {
        type: "string", title: "Exhibit caption", minLength: 1,
        "x-signaldeck-schema": "signaldeck.schema/2",
        default: "Draft exhibit", examples: ["Public exhibit"],
      },
    },
    required: [field],
  };
  const outputSchema = {
    type: "object",
    properties: { [output]: { type: "string" }, [group]: { type: "string" } },
    required: [output, group],
  };
  return { field, output, group, manifestSource: stringify({
    apiVersion: "signaldeck.workflowPackage/v2",
    metadata: { key, name: `Exhibition ${key}` },
    agents: {
      curator: {
        inputSchema, outputSchema,
        strategy: { kind: "model", modelRef: model, prompt: "Describe the supplied exhibit using the output contract." },
      },
    },
    workflows: {
      exhibit: {
        name: `Curate ${key}`, description: "A newly imported workflow with no compiled catalog entry.",
        inputSchema, outputSchema,
        nodes: { label: { uses: "curator", inputMapping: { ref: "workflow.input" } } },
        outputMapping: { ref: "nodes.label.output" },
        presentation: {
          version: "signaldeck.presentation/1",
          inputHints: [{ ref: `workflow.input.${field}`, control: "textarea", placeholder: "Describe this exhibit" }],
          title: { kind: "input", ref: `workflow.input.${field}` },
          sections: [
            { kind: "markdown", ref: `nodes.label.output.${output}`, label: "Exhibit text", required: true },
            { kind: "value", ref: `workflow.output.${group}`, label: "Shelf value", required: true },
          ],
        },
      },
    },
  }, { aliasDuplicateObjects: false }) };
}

async function readRun(request: APIRequestContext, id: string) {
  const response = await request.get(`${apiBase}/runs/${id}`);
  expect(response.ok(), await response.text()).toBeTruthy();
  return response.json();
}

for (const renamed of [false, true]) {
  test(`D01-D04/D06: imported ${renamed ? "renamed" : "business-name collision"} fields drive ordinary form and frozen result`, async ({ page, request }) => {
    test.setTimeout(150_000);
    const { key: resourceKey, model } = await seed(request);
    const key = `exhibit-${resourceKey}`;
    const fixture = source(key, model, renamed);
    const imported = await request.post(`${apiBase}/workflow-packages/import`, {
      data: { sources: [{ name: "exhibit.yaml", manifestSource: fixture.manifestSource }], mode: "missing_only" },
    });
    expect(imported.ok(), await imported.text()).toBeTruthy();
    expect((await imported.json()).items).toEqual([
      expect.objectContaining({ packageKey: key, status: "created" }),
    ]);
    await page.goto("/tasks");
    const card = page.locator("section").filter({ has: page.getByRole("heading", { name: `Curate ${key}`, exact: true }) }).last();
    await card.getByRole("link", { name: "选择任务", exact: true }).click();
    const caption = page.getByRole("textbox", { name: "Exhibit caption", exact: true });
    await expect(caption).toHaveValue("Draft exhibit");
    await expect(caption).toHaveAttribute("placeholder", "Describe this exhibit");
    expect(await caption.evaluate((element) => element.tagName)).toBe("TEXTAREA");
    await caption.fill("Explicit exhibit caption");
    await page.getByRole("switch", { name: "专家模式", exact: true }).check();
    await page.getByRole("switch", { name: "专家模式", exact: true }).uncheck();
    await expect(caption).toHaveValue("Explicit exhibit caption");
    if (!renamed) {
      await page.getByText("保存常用输入或收藏任务（可选）", { exact: true }).click();
      await page.getByLabel("配置名称").fill(`Exhibit preset ${key}`);
      const saving = page.waitForResponse((response) => response.url() === `${apiBase}/task-presets` && response.request().method() === "POST");
      await page.getByRole("button", { name: "保存为新配置", exact: true }).click();
      const saved = await saving;
      expect(saved.ok(), await saved.text()).toBeTruthy();
      const preset = await saved.json();
      expect(preset.parameters).toEqual({ [fixture.field]: "Explicit exhibit caption" });
      await page.goto(`/tasks/new?presetId=${preset.id}`);
      await expect(caption).toHaveValue("Explicit exhibit caption");
    }
    await page.getByRole("button", { name: "开始任务", exact: true }).click();
    await expect(page).toHaveURL(/\/runs\/[^/?]+$/);
    const id = new URL(page.url()).pathname.split("/").at(-1)!;
    await expect.poll(async () => (await readRun(request, id)).status, { timeout: 60_000 }).toBe("succeeded");
    const frozen = await readRun(request, id);
    expect(frozen.spec.parameters).toEqual({ [fixture.field]: "Explicit exhibit caption" });
    await page.reload();
    await expect(page.getByRole("region", { name: "Exhibit text", exact: true })).toContainText(`fake provider ${fixture.output}`);
    await expect(page.getByRole("region", { name: "Shelf value", exact: true })).toContainText(`fake provider ${fixture.group}`);
    await expect(page.getByRole("link", { name: /Finance|打开报告/ })).toHaveCount(0);
    const result = await (await request.get(`${apiBase}/runs/${id}/result`)).json();
    expect(result.title).toBe("Explicit exhibit caption");
    expect(result.contentStatus).toBe("available");
    expect(result.sections).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "markdown", label: "Exhibit text", value: `fake provider ${fixture.output}`, nodeId: "label" }),
      expect.objectContaining({ kind: "value", label: "Shelf value", value: `fake provider ${fixture.group}` }),
    ]));
    expect(result.sections.some((section: { kind: string }) => section.kind === "link")).toBe(false);
    const replaced = await request.post(`${apiBase}/workflow-packages/import`, {
      data: { sources: [{ manifestSource: fixture.manifestSource.replace("Exhibit text", "New revision heading") }], mode: "update" },
    });
    expect(replaced.ok(), await replaced.text()).toBeTruthy();
    expect((await replaced.json()).items[0].status).toBe("updated");
    await page.reload();
    await expect(page.getByRole("region", { name: "Exhibit text", exact: true })).toBeVisible();
    expect((await readRun(request, id)).spec).toEqual(frozen.spec);
    await page.getByRole("link", { name: "修改输入后开始", exact: true }).click();
    await expect(caption).toHaveValue("Explicit exhibit caption");
    await expect(caption).toHaveAttribute("placeholder", "Describe this exhibit");
    if (!renamed) {
      await page.getByRole("button", { name: "设置重复执行", exact: true }).click();
      await expect(caption).toHaveValue("Explicit exhibit caption");
      await page.getByLabel("安排名称").fill(`Exhibit schedule ${key}`);
      await page.getByRole("combobox", { name: "自动执行状态", exact: true }).click();
      await page.getByRole("option", { name: "已暂停", exact: true }).click();
      const saving = page.waitForResponse((response) => response.url() === `${apiBase}/schedules` && response.request().method() === "POST");
      await page.getByRole("button", { name: "启用自动执行", exact: true }).click();
      const saved = await saving;
      expect(saved.ok(), await saved.text()).toBeTruthy();
      const schedule = await saved.json();
      expect(schedule.parameters).toEqual({ [fixture.field]: "Explicit exhibit caption" });
      await expect.poll(async () => (await (await request.get(`${apiBase}/schedules/${schedule.id}`)).json()).syncStatus, { timeout: 30_000 }).toBe("synced");
      await page.getByRole("button", { name: "立即执行", exact: true }).click();
      await expect(page.getByText("已接受执行请求", { exact: true })).toBeVisible();
      let scheduledId = "";
      await expect.poll(async () => {
        const runs = await (await request.get(`${apiBase}/runs`)).json();
        const scheduled = runs.items.find((run: { origin: { scheduleId?: string } }) => run.origin.scheduleId === schedule.id);
        scheduledId = scheduled?.id ?? "";
        return scheduled?.status;
      }, { timeout: 60_000 }).toBe("succeeded");
      const scheduledRun = await readRun(request, scheduledId);
      expect(scheduledRun.spec.parameters).toEqual({ [fixture.field]: "Explicit exhibit caption" });
      expect(scheduledRun.origin.scheduleId).toBe(schedule.id);
    }
  });
}

test("D02: concurrent missing-only imports preserve the winning revision and isolate invalid sources", async ({ request }) => {
  const { key: resourceKey, model } = await seed(request);
  const key = `import-${resourceKey}`;
  const fixture = source(key, model, false);
  const variants = [fixture.manifestSource, fixture.manifestSource.replace("Draft exhibit", "Other draft")];
  const imports = await Promise.all(variants.map((manifestSource) => request.post(`${apiBase}/workflow-packages/import`, {
    data: { sources: [{ manifestSource }], mode: "missing_only" },
  })));
  const results = [];
  for (const imported of imports) {
    expect(imported.ok(), await imported.text()).toBeTruthy();
    results.push((await imported.json()).items[0]);
  }
  expect(results.map((item) => item.status).sort()).toEqual(["created", "preserved"]);
  const saved = await (await request.get(`${apiBase}/workflow-packages/${key}`)).json();
  const mixed = await request.post(`${apiBase}/workflow-packages/import`, {
    data: { sources: [{ manifestSource: "not: [valid" }, { manifestSource: fixture.manifestSource.replace("Draft exhibit", "Should never win") }], mode: "missing_only" },
  });
  expect(mixed.ok(), await mixed.text()).toBeTruthy();
  expect((await mixed.json()).items.map((item: { status: string }) => item.status)).toEqual(["error", "preserved"]);
  const unchanged = await (await request.get(`${apiBase}/workflow-packages/${key}`)).json();
  expect(unchanged.packageHash).toBe(saved.packageHash);
  expect(unchanged.source).toBe(saved.source);
  const valid = await request.post(`${apiBase}/workflow-packages/validate-manifest`, { data: { manifestSource: unchanged.source } });
  expect((await valid.json()).contentHash).toBe(saved.packageHash);
});
