import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { RunPage } from "./runs";
import { runFixture } from "./fixtures";

afterEach(() => vi.unstubAllGlobals());
it("opens an exact source operation through a readable link without showing execution envelopes", async () => {
  const run = structuredClone(runFixture);
  run.spec.definition.agents.assistant.name = "整理资料";
  run.evidence[2].output = { rawApiKey: "internal-response" };
  run.evidence[2].metadata = { storagePath: "/private/runtime/operation", apiResponse: { headers: "raw-headers" } };
  run.evidence[2].errorCode = "effect_unconfirmed";
  run.hasUnknownEffects = true;
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith("/result") ? {
    runId: run.id, sections: [], attachments: [], freshness: [], status: "running", contentStatus: "unknown",
  } : run), { headers: { "content-type": "application/json" } })));
  const router = createMemoryRouter([{ path: "/runs/:runId", element: <RunPage /> }], { initialEntries: ["/runs/run-1?tab=evidence&operation=operation-stable"] });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RouterProvider router={router} /></QueryClientProvider>);
  const selected = await screen.findByRole("region", { name: "所选操作详情" });
  expect(within(selected).getByRole("heading", { name: "服务操作 1" })).toBeVisible();
  expect(within(selected).getByText(/尚未确认是否产生了外部更改/)).toBeVisible();
  expect(within(selected).queryByText(/执行失败|具体原因未知/)).not.toBeInTheDocument();
  expect(screen.getByText("保存状态待核实")).toBeVisible();
  for (const tab of ["步骤进度", "本次设置", "资料与附件", "执行过程"]) {
    fireEvent.mouseDown(screen.getByRole("tab", { name: tab }), { button: 0, ctrlKey: false });
    expect(document.body.textContent).not.toMatch(/run-1|operation-stable|sha256:|rawApiKey|internal-response|private\/runtime|raw-headers/);
  }
});


function mountRun(run: typeof runFixture, sections: import("@/lib/types/result").ResultSection[] = [], search = "tab=evidence&target=node-1", errorCode?: string) {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => new Response(JSON.stringify(url.endsWith("/result") ? { runId: run.id, sections, attachments: [], freshness: [], status: run.status, contentStatus: "available", errorCode: errorCode ?? run.errorCode } : run), { headers: { "content-type": "application/json" } })));
  const router = createMemoryRouter([{ path: "/runs/:runId", element: <RunPage /> }], { initialEntries: [`/runs/run-1?${search}`] });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RouterProvider router={router} /></QueryClientProvider>);
  return router;
}
it.each([true, false])("uses a frozen business title or effect label instead of protocol documentation: title=%s", async (titled) => {
  const run = structuredClone(runFixture);
  const toolId = "example/notes/search";
  run.evidence[2].toolId = toolId;
  run.spec.definition.agents.assistant.tools = [toolId];
  run.spec.pluginReleases = [{ tools: [{ toolId, effect: "read", description: "includeDerived sourceNoteIds literal protocol implementation", inputSchema: titled ? { type: "object", title: "查找笔记" } : { type: "object" } }] }];
  mountRun(run, [], "tab=evidence&target=tool-1");
  const label = titled ? "查找笔记" : "读取资料 1";
  const detail = await screen.findByRole("region", { name: "所选操作详情" });
  expect(within(detail).getByRole("heading", { name: label })).toBeVisible();
  expect(document.body.textContent).not.toMatch(/includeDerived|sourceNoteIds|literal protocol/);
  fireEvent.mouseDown(screen.getByRole("tab", { name: "本次设置" }), { button: 0, ctrlKey: false });
  expect(await screen.findByText(`${label} · 只读`)).toBeVisible();
  expect(document.body.textContent).not.toMatch(/includeDerived|sourceNoteIds|literal protocol/);
});
it("inspects frozen input sources and confirmed upstream content without showing intermediate API values", async () => {
  const run = structuredClone(runFixture);
  const original = "用户原始代码：schema.sourceNoteIds = 42;";
  run.spec.parameters = { text: original };
  run.spec.definition.workflows.main.inputSchema = { type: "object", properties: { text: { type: "string", title: "原文" } } };
  run.spec.definition.agents.reader = { ...run.spec.definition.agents.assistant, name: "查找资料" };
  run.spec.definition.agents.assistant.name = "整理资料";
  run.spec.definition.agents.assistant.inputSchema = { type: "object", properties: { priorNotes: { type: "object" }, text: { type: "string", title: "待整理原文" } } };
  run.spec.definition.workflows.main.nodes.lookup = { uses: "reader", inputMapping: { ref: "workflow.input" } };
  run.spec.definition.workflows.main.nodes.answer.inputMapping = { object: { priorNotes: { ref: "nodes.lookup.output" }, text: { ref: "workflow.input.text" } } };
  run.spec.plan.nodeOrder = ["lookup", "answer"];
  run.spec.plan.dependencies = { lookup: [], answer: ["lookup"] };
  run.evidence[0].input = { priorNotes: { sourceNoteIds: ["middle-api-id"], storedPath: "/private/intermediate" }, text: original };
  run.evidence.unshift({ ...run.evidence[0], id: "lookup-evidence", nodeId: "lookup", status: "succeeded", input: run.spec.parameters, output: { sourceNoteIds: ["middle-api-id"] } });
  mountRun(run, [{ kind: "markdown", label: "相关资料", value: "经确认的来源正文", nodeId: "lookup", evidenceId: "lookup-evidence" }]);
  const sources = await screen.findByRole("region", { name: "步骤的信息来源" });
  expect(within(sources).getByText("用户填写的信息 › 原文")).toBeVisible();
  expect(document.body.textContent).not.toMatch(/priorNotes|middle-api-id|private\/intermediate/);
  expect(screen.queryByText(original)).not.toBeInTheDocument();
  fireEvent.click(await screen.findByRole("link", { name: "查看查找资料的已确认内容" }));
  expect(await screen.findByText("经确认的来源正文")).toBeVisible();
  expect(document.body.textContent).not.toMatch(/priorNotes|middle-api-id|private\/intermediate/);
  fireEvent.click(screen.getByRole("link", { name: "查看本次填写的信息" }));
  expect(await screen.findByText(original)).toBeVisible();
  expect(document.body.textContent).not.toMatch(/priorNotes|middle-api-id|private\/intermediate/);
});


it("uses the projected known failure in the execution header while leaving the model reply unpromoted", async () => {
  const run = structuredClone(runFixture);
  run.status = "failed";
  run.errorCode = "workflow_nodes_failed";
  run.evidence[0].status = "failed";
  run.evidence[0].errorCode = "agent_output_invalid";
  run.evidence[1].status = "failed";
  run.evidence[1].errorCode = "agent_output_invalid";
  run.evidence[2].kind = "model";
  run.evidence[2].status = "succeeded";
  run.evidence[2].output = "unconfirmed raw reply";
  mountRun(run, [], "tab=evidence&target=node-1", "agent_output_invalid");
  await screen.findByRole("region", { name: "所选操作详情" });
  await waitFor(() => expect(screen.getAllByText("模型没有按任务要求提供可用结果。可以重试，或检查助手的结果要求。")).toHaveLength(2));
  expect(screen.queryByText(/具体原因未知/)).not.toBeInTheDocument();
  expect(screen.queryByText("unconfirmed raw reply")).not.toBeInTheDocument();
});

it.each([
  ["failed", "执行失败", "danger"],
  ["timed_out", "执行超时", "danger"],
  ["unknown", "结果未确认", "warning"],
  ["succeeded", "已完成", "success"],
] as const)("keeps %s step and operation status tones consistent", async (status, label, tone) => {
  const run = structuredClone(runFixture);
  run.evidence[0].status = status;
  run.evidence[1].status = status;
  mountRun(run, [], "tab=graph");
  const steps = await screen.findByRole("list", { name: "任务步骤" });
  expect(within(steps).getByText(label)).toHaveAttribute("data-tone", tone);
  fireEvent.mouseDown(screen.getByRole("tab", { name: "执行过程" }), { button: 0, ctrlKey: false });
  const evidence = screen.getByLabelText("步骤与服务操作");
  for (const badge of within(evidence).getAllByText(label)) {
    expect(badge).toHaveAttribute("data-tone", tone);
  }
});
