import { expect, test } from "@playwright/test";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { parse, stringify } from "yaml";
import { apiBase } from "./platform-fixtures";
import { startHeldPlugin } from "./held-plugin-fixture";

test("actual independent write remains unknown after cancellation and history survives plugin shutdown", async ({page,request}, testInfo) => {
  test.setTimeout(150000);
  const plugin = await startHeldPlugin(request);
  const directory = resolve("../output/playwright/faults");
  mkdirSync(directory,{recursive:true});
  try {
    const install = await request.post(`${apiBase}/plugins`,{data:{release:plugin.binding,enabled:true}});
    expect(install.ok(),await install.text()).toBe(true);
    const key = `unknown-${crypto.randomUUID().slice(0,8)}`;
    const tool = plugin.binding.tools[0];
    const source = stringify({
      apiVersion:"signaldeck.workflowPackage/v2",metadata:{key,name:"保存状态核实"},
      agents:{writer:{name:"保存业务记录",inputSchema:tool.inputSchema,outputSchema:tool.outputSchema,
        strategy:{kind:"deterministic",toolId:tool.toolId,inputMapping:{ref:"agent.input"},outputMapping:{ref:"tool.output"}},tools:[tool.toolId],resources:[]}},
      workflows:{main:{name:"保存业务记录",inputSchema:tool.inputSchema,outputSchema:tool.outputSchema,
        nodes:{write:{uses:"writer",inputMapping:{ref:"workflow.input"}},after:{uses:"writer",inputMapping:{ref:"nodes.write.output"}}},
        outputMapping:{ref:"nodes.after.output"},deadlineSeconds:120}},
    },{aliasDuplicateObjects:false});
    const created = await request.post(`${apiBase}/workflow-packages`,{data:{manifestSource:source}});
    expect(created.ok(),await created.text()).toBe(true);
    const launched = await request.post(`${apiBase}/workflow-packages/${key}/launches`,{data:{workflowKey:"main",parameters:{value:1,delay:0,tag:"Controlled external effect"},launchId:crypto.randomUUID()}});
    expect(launched.ok(),await launched.text()).toBe(true);
    const runId = (await launched.json()).id;
    await expect.poll(() => existsSync(join(plugin.directory,"started.json")),{timeout:60000}).toBe(true);
    await page.goto(`/runs/${runId}`);
    await page.getByRole("button",{name:"取消本次运行",exact:true}).click();
    await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${runId}`)).json()).status,{timeout:30000}).toBe("cancelled");
    await expect(page.getByText("保存状态待核实",{exact:true})).toBeVisible();
    await expect(page.getByText("服务尚未确认是否保存成功。请先检查执行证据或目标位置，避免重复保存。",{exact:true})).toBeVisible();
    const before = await (await request.get(`${apiBase}/runs/${runId}`)).json();
    const unknown = before.evidence.find((item:{kind:string;status:string}) => item.kind === "tool" && item.status === "unknown");
    expect(unknown).toBeTruthy();
    expect(unknown.output).toBeNull();
    expect(before.output).toBeNull();
    expect(existsSync(join(plugin.directory,"effect.json"))).toBe(false);
    await page.getByRole("button",{name:"再运行一次",exact:true}).click();
    await expect(page.getByRole("button",{name:"确认并开始新运行",exact:true})).toBeDisabled();
    await expect(page.getByLabel("我已核实目标位置与执行证据，确认需要再次执行")).not.toBeChecked();
    await page.screenshot({path:join(directory,"unknown-repeat-guard.png"),fullPage:true});
    writeFileSync(join(plugin.directory,"release"), "");
    await expect.poll(() => existsSync(join(plugin.directory,"effect.json")),{timeout:10000}).toBe(true);
    const effect = JSON.parse(readFileSync(join(plugin.directory,"effect.json"),"utf8"));
    expect(effect.operationId).toBe(unknown.operationId);
    expect(effect.output.value).toBe(2);
    const confirmedKey = `${key}-confirmed`;
    const confirmedSource = stringify({ ...parse(source), metadata: { key: confirmedKey, name: "Confirmed offline record" } }, { aliasDuplicateObjects: false });
    const savedConfirmed = await request.post(`${apiBase}/workflow-packages`, { data: { manifestSource: confirmedSource } });
    expect(savedConfirmed.ok(), await savedConfirmed.text()).toBe(true);
    const confirmedLaunch = await request.post(`${apiBase}/workflow-packages/${confirmedKey}/launches`, { data: { workflowKey: "main", parameters: { value: 10, delay: 0, tag: "Confirmed offline output" }, launchId: crypto.randomUUID() } });
    expect(confirmedLaunch.ok(), await confirmedLaunch.text()).toBe(true);
    const confirmedId = (await confirmedLaunch.json()).id;
    await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${confirmedId}`)).json()).status, { timeout: 60000 }).toBe("succeeded");
    const confirmedRun = await (await request.get(`${apiBase}/runs/${confirmedId}`)).json();
    const confirmedResult = await (await request.get(`${apiBase}/runs/${confirmedId}/result`)).json();
    expect(confirmedRun.output).toEqual({ value: 12, delay: 0, tag: "Confirmed offline output" });
    expect(confirmedResult.sections).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "value", label: "工作流输出", value: confirmedRun.output }),
      expect.objectContaining({ kind: "value", nodeId: "after", pluginId: plugin.binding.pluginId, operationId: expect.any(String), value: confirmedRun.output }),
    ]));
    const largeText = "large-confirmed-content-".repeat(4000);
    const largeKey = `${key}-large`;
    const largeDefinition = parse(source);
    largeDefinition.metadata = { key: largeKey, name: "Large frozen output" };
    largeDefinition.workflows.main.presentation = {
      version: "signaldeck.presentation/1",
      sections: [{ kind: "markdown", label: "大正文", ref: "nodes.after.output.tag", required: true }],
    };
    const savedLarge = await request.post(`${apiBase}/workflow-packages`, { data: { manifestSource: stringify(largeDefinition, { aliasDuplicateObjects: false }) } });
    expect(savedLarge.ok(), await savedLarge.text()).toBe(true);
    const largeLaunch = await request.post(`${apiBase}/workflow-packages/${largeKey}/launches`, { data: { workflowKey: "main", parameters: { value: 20, delay: 0, tag: largeText }, launchId: crypto.randomUUID() } });
    expect(largeLaunch.ok(), await largeLaunch.text()).toBe(true);
    const largeId = (await largeLaunch.json()).id;
    await expect.poll(async () => (await (await request.get(`${apiBase}/runs/${largeId}`)).json()).status, { timeout: 60000 }).toBe("succeeded");
    const largeResult = await (await request.get(`${apiBase}/runs/${largeId}/result`)).json();
    expect(largeResult.deferredSections).toContain("大正文");
    expect(largeResult.attachments.length).toBeGreaterThan(0);
    await plugin.stop();
    expect(await request.get(`${plugin.baseUrl}/health`,{timeout:500}).catch(() => null)).toBeNull();
    await page.reload();
    await expect(page.getByText("保存状态待核实",{exact:true})).toBeVisible();
    expect(await (await request.get(`${apiBase}/runs/${runId}`)).json()).toEqual(before);
    await page.getByRole("link",{name:"核实未确认的操作",exact:true}).click();
    await expect(page.getByLabel("Call ownership tree")).toBeVisible();
    await page.screenshot({path:join(directory,"plugin-offline-call-evidence.png"),fullPage:true});
    await page.goto(`/runs/${confirmedId}`);
    await expect(page.getByRole("region", { name: "工作流输出", exact: true })).toContainText("Confirmed offline output");
    expect(await (await request.get(`${apiBase}/runs/${confirmedId}`)).json()).toEqual(confirmedRun);
    expect(await (await request.get(`${apiBase}/runs/${confirmedId}/result`)).json()).toEqual(confirmedResult);
    const requests = readFileSync(join(plugin.directory,"requests.jsonl"),"utf8").trim().split("\n").map(line => JSON.parse(line));
    const writes = requests.filter(item => item.method === "tools/call" && item.params.name === tool.toolId);
    expect(writes).toHaveLength(5);
    expect(writes.filter(item => item.params.arguments.tag === "Controlled external effect")).toHaveLength(1);
    expect(writes.filter(item => item.params.arguments.tag === "Confirmed offline output")).toHaveLength(2);
    const history = await (await request.get(`${apiBase}/runs`,{params:{packageKey:key}})).json();
    expect(history.total).toBe(1);
    let engineStopped = false;
    const controlFile = process.env.SIGNALDECK_E2E_CONTROL_FILE;
    if (process.env.SIGNALDECK_E2E_ALLOW_ENGINE_STOP === "1" && controlFile) {
      const control = JSON.parse(readFileSync(controlFile,"utf8"));
      expect(control.status).toBe("running");
      expect(control.requestPath).toBe(`${controlFile}.request`);
      writeFileSync(control.requestPath,JSON.stringify({nonce:control.nonce,action:"stop_temporal"}),{flag:"wx"});
      await expect.poll(() => JSON.parse(readFileSync(controlFile,"utf8")).status,{timeout:15000}).toBe("temporal_stopped");
      engineStopped = true;
      await page.goto(`/runs/${runId}`);
      await expect(page.getByText("保存状态待核实",{exact:true})).toBeVisible();
      expect(await (await request.get(`${apiBase}/runs/${runId}`)).json()).toEqual(before);
      expect((await (await request.get(`${apiBase}/runs`,{params:{packageKey:key}})).json()).total).toBe(1);
      await page.getByRole("link",{name:"核实未确认的操作",exact:true}).click();
      await expect(page.getByLabel("Call ownership tree")).toBeVisible();
      await page.screenshot({path:join(directory,"engine-and-plugin-offline-history.png"),fullPage:true});
      await page.goto(`/runs/${confirmedId}`);
      await expect(page.getByRole("region", { name: "工作流输出", exact: true })).toContainText("Confirmed offline output");
      expect(await (await request.get(`${apiBase}/runs/${confirmedId}`)).json()).toEqual(confirmedRun);
      expect(await (await request.get(`${apiBase}/runs/${confirmedId}/result`)).json()).toEqual(confirmedResult);
    }
    // Export, annotation, updates and comparison must still use persisted facts.
    await page.goto(`/runs/${confirmedId}`);
    const downloaded = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出 Markdown", exact: true }).click();
    const markdown = await downloaded;
    expect(await markdown.failure()).toBeNull();
    const exportedPath = join(directory, "offline-confirmed.md");
    await markdown.saveAs(exportedPath);
    expect(readFileSync(exportedPath, "utf8")).toContain("Confirmed offline output");
    expect(readFileSync(exportedPath, "utf8")).toContain(confirmedId);
    await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
    await page.getByRole("button", { name: "复制所选正文", exact: true }).click();
    await expect(page.getByText("所选确认内容已复制。", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(readFileSync(exportedPath, "utf8"));
    const annotated = await request.patch(`${apiBase}/runs/${confirmedId}/metadata`, {
      data: { expectedRevision: 0, isFavorite: true, note: "Retained while execution services are offline" },
    });
    expect(annotated.ok(), await annotated.text()).toBe(true);
    expect(await (await request.get(`${apiBase}/runs/${confirmedId}`)).json()).toEqual(confirmedRun);
    const updates = await (await request.get(`${apiBase}/attention?view=all`)).json();
    const unresolvedUpdate = updates.items.find((item: { runId: string }) => item.runId === runId);
    expect(unresolvedUpdate.hasUnknownEffects).toBe(true);
    const viewed = await request.patch(`${apiBase}/attention/${unresolvedUpdate.id}`, {
      data: { expectedRevision: unresolvedUpdate.revision, isRead: true },
    });
    expect(viewed.ok(), await viewed.text()).toBe(true);
    const remainingUpdates = await (await request.get(`${apiBase}/attention`)).json();
    expect(remainingUpdates.items).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: unresolvedUpdate.id, isRead: true, hasUnknownEffects: true }),
    ]));
    await page.goto(`/runs/compare?left=${confirmedId}&right=${runId}&leftSection=section:0`);
    await expect(page.getByRole("region", { name: "左侧结果", exact: true })).toContainText("Confirmed offline output");
    await expect(page.getByRole("region", { name: "右侧结果", exact: true })).toContainText("保存状态待核实");
    await expect(page.getByRole("region", { name: "右侧结果", exact: true })).toContainText("此运行没有可比较的确认正文");
    await page.screenshot({ path: join(directory, "offline-comparison.png"), fullPage: true });
    expect(await (await request.get(`${apiBase}/runs/${runId}`)).json()).toEqual(before);
    const artifactRequests: string[] = [];
    page.on("request", (req) => { if (req.url().includes("/api/artifacts/")) artifactRequests.push(req.url()); });
    await page.goto(`/runs/${largeId}`);
    await expect(page.getByRole("region", { name: "复制与导出", exact: true })).toBeVisible();
    expect(artifactRequests).toHaveLength(0);
    await page.getByText(/^选择复制与导出的内容/).click();
    await page.getByRole("checkbox", { name: /^读取并选入附件：/ }).first().check();
    await expect(page.getByRole("button", { name: "导出 Markdown", exact: true })).toBeEnabled();
    expect(artifactRequests.length).toBeGreaterThan(0);
    const largeDownloadPromise = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出 Markdown", exact: true }).click();
    const largeDownload = await largeDownloadPromise;
    const largePath = join(directory, "offline-large.md");
    await largeDownload.saveAs(largePath);
    expect(readFileSync(largePath, "utf8")).toContain(largeText);
    expect(readFileSync(largePath, "utf8")).toContain("未纳入本文件的内容");
    expect(readFileSync(largePath, "utf8")).toContain("延后解析的声明");
    await page.goto(`/runs/compare?left=${largeId}&right=${confirmedId}&leftSection=artifact:0:0&rightSection=section:0`);
    await expect(page.getByRole("button", { name: "读取左侧所选附件", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "读取左侧所选附件", exact: true }).click();
    await expect(page.getByRole("region", { name: "左侧结果", exact: true })).toContainText("large-confirmed-content-");
    const observation = {engineStopped,run:before,effectAfterCancellation:effect,confirmedRun,confirmedResult,pluginStopped:true,writeRequests:writes,methods:requests.map(item => item.method),exportedPath,largeId,largeResult,largePath,artifactRequests,annotation:await annotated.json(),unresolvedUpdate:await viewed.json()};
    writeFileSync(join(directory,"unknown-plugin-offline-evidence.json"),JSON.stringify(observation,null,2));
    await testInfo.attach("unknown-plugin-offline-evidence.json",{body:JSON.stringify(observation,null,2),contentType:"application/json"});
  } finally { await plugin.dispose(); }
});
