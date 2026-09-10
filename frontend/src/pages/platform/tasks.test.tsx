import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { TaskPage, TasksPage } from "./tasks";
import { ApiRequestError } from "@/lib/api-client";
import type { ReuseInput, TaskPreset } from "@/lib/types/task-experience";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
const mocks = vi.hoisted(() => ({
  saveDraft: vi.fn(),
  getDraft: vi.fn(),
  prepare: vi.fn(),
  launch: vi.fn(),
  save: vi.fn(),
  expert: false,
  hash: 0,
  historical: undefined as ReuseInput | undefined,
  preset: undefined as TaskPreset | undefined,
  schema: undefined as JsonObject | undefined,
}));
vi.mock("@/lib/api/task-drafts", () => ({
  taskDraftApi: { list: async () => ({ items: [] }), get: (id: string) => mocks.getDraft(id), save: (input: unknown) => mocks.saveDraft(input), delete: async () => undefined },
}));
vi.mock("@/hooks/use-display-mode", () => ({
  useDisplayMode: () => ({ expert: mocks.expert }),
}));
vi.mock("@/hooks/use-results", () => ({
  useResultHistory: () => ({ data: { items: [] } }),
}));
vi.mock("@/hooks/use-workflow-platform", () => ({
  usePackages: () => ({
    data: {
      items: [
        {
          key: "research_notes",
          packageHash: `test-${mocks.hash}`,
          definition: {
            metadata: { key: "research_notes", name: "Notes" },
            workflows: {
              capture: {
                name: "保存原文",
                presentation: { version: "signaldeck.presentation/1", inputHints: [{ref: "workflow.input.text", control: "textarea"}] },
                inputSchema: mocks.schema ?? {
                  type: "object",
                  properties: {
                    title: { type: "string", title: "标题", minLength: 1 },
                    text: { type: "string", title: "原文" },
                  },
                  required: ["title", "text"],
                },
              },
            },
          },
        },
      ],
    },
  }),
  usePlatformMutations: () => ({ saveResource: { mutateAsync: vi.fn() } }),
}));
vi.mock("@/lib/api/task-experience", () => ({
  taskExperienceApi: { prepare: (input: unknown) => mocks.prepare(input) },
}));
vi.mock("@/hooks/use-task-experience", async (importOriginal) => ({
  ...await importOriginal<typeof import("@/hooks/use-task-experience")>(),
  useTaskPresets: () => ({ data: { items: mocks.preset ? [mocks.preset] : [] } }),
  useTaskReuse: () => ({ data: mocks.historical }),
  useConnectionPresets: () => ({ data: { items: [] } }),
  useTaskMutations: () => ({
    prepare: { mutateAsync: mocks.prepare },
    launch: { mutateAsync: mocks.launch },
    savePreset: { mutateAsync: mocks.save },
  }),
}));
function CurrentPath() { const location = useLocation(); return <output aria-label="Current route">{location.pathname}{location.search}</output>; }
function Page({ path = "/tasks/new?packageKey=research_notes&workflowKey=capture" }: { path?: string }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }));
  return (
    <QueryClientProvider client={client}>
    <MemoryRouter
      initialEntries={[
        path,
      ]}
    >
      <CurrentPath />
      {path === "/tasks" ? <TasksPage /> : <TaskPage />}
    </MemoryRouter>
    </QueryClientProvider>
  );
}
beforeEach(() => {
  mocks.hash++;
  mocks.getDraft.mockReset();
  mocks.saveDraft.mockReset().mockImplementation(async (input) => {
    const saved = { ...input, revision: input.revision + 1, workflow: { name: "保存原文", inputSchema: mocks.schema ?? { type: "object", properties: { title: { type: "string", title: "标题" }, text: { type: "string", title: "原文" } }, required: ["title", "text"] } } };
    mocks.getDraft.mockResolvedValue(saved);
    return saved;
  });
  mocks.expert = false;
  mocks.historical = undefined;
  mocks.preset = undefined;
  mocks.schema = undefined;
  mocks.save.mockReset().mockResolvedValue({});
  mocks.prepare.mockReset().mockResolvedValue({
    packageHash: `test-${mocks.hash}`,
    ready: true,
    bindingToken: "approved",
    requirements: [],
    issues: [],
    changedBindings: [],
    effectiveSettings: {},
    previousBindings: {},
  });
  mocks.launch.mockReset();
});
it("shows the catalog authoring entry only in expert mode while keeping ordinary tasks", () => {
  const view = render(<Page path="/tasks" />);
  const taskHref = "/tasks/new?packageKey=research_notes&workflowKey=capture";
  expect(screen.getByRole("link", { name: "选择任务" })).toHaveAttribute("href", taskHref);
  expect(screen.queryByRole("link", { name: "全部任务定义与专家制作" })).not.toBeInTheDocument();
  mocks.expert = true;
  view.rerender(<Page path="/tasks" />);
  expect(screen.getByRole("link", { name: "全部任务定义与专家制作" })).toHaveAttribute("href", "/workflow-packages");
  expect(screen.getByRole("link", { name: "选择任务" })).toHaveAttribute("href", taskHref);
  mocks.expert = false;
  view.rerender(<Page path="/tasks" />);
  expect(screen.queryByRole("link", { name: "全部任务定义与专家制作" })).not.toBeInTheDocument();
  expect(mocks.prepare).not.toHaveBeenCalled();
  expect(mocks.launch).not.toHaveBeenCalled();
  expect(mocks.save).not.toHaveBeenCalled();
});
it("keeps a customized task discoverable in ordinary mode", () => {
  mocks.schema = {
    type: "object",
    properties: { title: { type: "string" }, text: { type: "string", title: "原文" }, extra: { type: "string" } },
    required: ["title", "text", "extra"],
  };
  render(<Page path="/tasks" />);
  expect(screen.getByRole("link", { name: "选择任务" })).toHaveAttribute("href", "/tasks/new?packageKey=research_notes&workflowKey=capture");
  expect(screen.queryByRole("link", { name: "全部任务定义与专家制作" })).not.toBeInTheDocument();
});
it.each([
  [null, { type: ["string", "null"], "x-signaldeck-schema": "signaldeck.schema/2", default: "authored default" }],
  [[], { type: "array", items: { type: "string" } }],
  ["scalar input", { type: "string" }],
  [0, { type: "number" }],
  [false, { type: "boolean" }],
] as [Json, JsonObject][])("restores and saves explicit preset input %j separately from a bookmark", async (parameters, schema) => {
  mocks.expert = true;
  mocks.schema = structuredClone(schema) as JsonObject;
  mocks.preset = {
    id: `preset-${mocks.hash}`,
    name: "可复用业务输入",
    packageKey: "research_notes",
    workflowKey: "capture",
    packageHash: `test-${mocks.hash}`,
    parameters: structuredClone(parameters),
    hasParameters: true,
    isFavorite: false,
    isPinned: false,
    currentPackageHash: `test-${mocks.hash}`,
    needsRevalidation: false,
    validationStatus: "valid",
    validationErrors: [],
  };
  render(<Page path={`/tasks/new?presetId=${mocks.preset.id}`} />);
  expect(screen.getByLabelText("Parameters JSON")).toHaveValue(JSON.stringify(parameters, null, 2));
  fireEvent.click(screen.getByText("保存常用输入或收藏任务（可选）"));
  fireEvent.click(screen.getByRole("button", { name: "更新此配置" }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(1));
  expect(mocks.save.mock.calls[0][0]).toMatchObject({ parameters, hasParameters: true });
  fireEvent.click(screen.getByRole("button", { name: "仅收藏任务，不保存输入" }));
  await waitFor(() => expect(mocks.save).toHaveBeenCalledTimes(2));
  expect(mocks.save.mock.calls[1][0]).toMatchObject({ parameters: null, hasParameters: false });
});
it("retains an explicit historical null instead of the current schema default", async () => {
  mocks.expert = true;
  mocks.historical = {
    workflow: { name: "Frozen task", inputSchema: { type: ["string", "null"] }, outputSchema: {}, nodes: {}, outputMapping: {} },
    sourceRunId: "nullable-original",
    packageKey: "nullable-task",
    workflowKey: "main",
    packageHash: "nullable-hash",
    parameters: null,
    inputSchema: { type: ["string", "null"], "x-signaldeck-schema": "signaldeck.schema/2", default: "authored default" },
  };
  render(<Page />);
  expect(screen.getByLabelText("Parameters JSON")).toHaveValue("null");
  await waitFor(() => expect(mocks.prepare).toHaveBeenCalled());
  expect(mocks.prepare.mock.calls[0][0].parameters).toBeNull();
});
it("shows effective settings automatically and starts with one user action", async () => {
  mocks.launch.mockResolvedValue({ id: "single-action-run" });
  render(<Page />);
  fireEvent.change(screen.getByLabelText("标题"), { target: { value: "一次开始" } });
  fireEvent.change(screen.getByLabelText("原文"), { target: { value: "保留业务原文" } });
  expect(await screen.findByRole("region", { name: "本次有效设置" })).toBeVisible();
  const start = screen.getByRole("button", { name: "开始任务" });
  await waitFor(() => expect(start).toBeEnabled());
  expect(screen.queryByRole("button", { name: "核对连接与本次设置" })).not.toBeInTheDocument();
  expect(mocks.launch).not.toHaveBeenCalled();
  fireEvent.click(start);
  await waitFor(() => expect(mocks.launch).toHaveBeenCalledTimes(1));
  expect(mocks.launch.mock.calls[0][0].parameters).toEqual({ title: "一次开始", text: "保留业务原文" });
});
it("lets experts recheck ready settings without changing the ordinary task input", async () => {
  const view = render(<Page />);
  await prepare();
  mocks.expert = true;
  view.rerender(<Page />);
  const callsBefore = mocks.prepare.mock.calls.length;
  const recheck = screen.getByRole("button", { name: "核对连接与本次设置" });
  expect(recheck).toBeEnabled();
  fireEvent.click(recheck);
  await waitFor(() => expect(mocks.prepare).toHaveBeenCalledTimes(callsBefore + 1));
  await waitFor(() => expect(screen.getByRole("button", { name: "核对连接与本次设置" })).toBeEnabled());
  mocks.expert = false;
  view.rerender(<Page />);
  expect(screen.queryByRole("button", { name: "核对连接与本次设置" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("标题")).toHaveValue("不变的标题");
  expect(screen.getByLabelText("原文")).toHaveValue("原始内容");
  expect(mocks.launch).not.toHaveBeenCalled();
});
it("lets an automatic preparation failure be retried before starting", async () => {
  const prepared = await mocks.prepare();
  mocks.prepare.mockReset().mockRejectedValue(new Error("Preparation unavailable"));
  render(<Page />);
  fireEvent.change(screen.getByLabelText("标题"), { target: { value: "保留标题" } });
  fireEvent.change(screen.getByLabelText("原文"), { target: { value: "保留原文" } });
  expect(await screen.findByText("Preparation unavailable")).toBeVisible();
  const recheck = screen.getByRole("button", { name: "核对连接与本次设置" });
  expect(recheck).toBeEnabled();
  mocks.prepare.mockResolvedValue(prepared);
  fireEvent.click(recheck);
  expect(await screen.findByRole("region", { name: "本次有效设置" })).toBeVisible();
  await waitFor(() => expect(screen.queryByRole("button", { name: "核对连接与本次设置" })).not.toBeInTheDocument());
  expect(screen.getByLabelText("标题")).toHaveValue("保留标题");
  expect(screen.getByLabelText("原文")).toHaveValue("保留原文");
  expect(mocks.launch).not.toHaveBeenCalled();
});
it("requires visible confirmation for automatically discovered binding changes", async () => {
  const prepared = await mocks.prepare();
  mocks.prepare.mockReset().mockResolvedValue({ ...prepared, changedBindings: ["resources"] });
  mocks.launch.mockResolvedValue({ id: "changed-binding-run" });
  render(<Page />);
  fireEvent.change(screen.getByLabelText("标题"), { target: { value: "核对保存位置" } });
  fireEvent.change(screen.getByLabelText("原文"), { target: { value: "原文" } });
  const confirm = await screen.findByRole("button", { name: "确认变化并开始" });
  expect(screen.getByText("与上次相比，连接或业务范围已变化，请核对后确认开始。")).toBeVisible();
  expect(mocks.launch).not.toHaveBeenCalled();
  fireEvent.click(confirm);
  await waitFor(() => expect(mocks.launch).toHaveBeenCalledTimes(1));
});
it("automatically exposes missing connections without starting or changing input", async () => {
  const prepared = await mocks.prepare();
  mocks.prepare.mockReset().mockResolvedValue({ ...prepared, ready: false, bindingToken: null, issues: ["resource_unavailable"] });
  render(<Page />);
  fireEvent.change(screen.getByLabelText("标题"), { target: { value: "保留标题" } });
  fireEvent.change(screen.getByLabelText("原文"), { target: { value: "保留原文" } });
  expect(await screen.findByText("尚需完成以下准备。填写的业务信息会保留。")).toBeVisible();
  expect(screen.getByRole("button", { name: "核对连接与本次设置" })).toBeEnabled();
  expect(screen.queryByRole("button", { name: "开始任务" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("标题")).toHaveValue("保留标题");
  expect(screen.getByLabelText("原文")).toHaveValue("保留原文");
  expect(mocks.launch).not.toHaveBeenCalled();
});
async function prepare() {
  fireEvent.change(screen.getByLabelText("标题"), {
    target: { value: "不变的标题" },
  });
  fireEvent.change(screen.getByLabelText("原文"), {
    target: { value: "原始内容" },
  });
  await waitFor(() => expect(screen.getByRole("button", { name: "开始任务" })).toBeEnabled());
}
it("restores an uncertain submission after remount and retries the same identity without input edits", async () => {
  mocks.launch.mockRejectedValue(new TypeError("Network response lost"));
  const view = render(<Page />);
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "开始任务" }));
  await screen.findByRole("button", { name: "使用同一请求重试" });
  view.unmount();
  render(<Page />);
  expect(screen.getByRole("button", { name: "使用同一请求重试" })).toBeEnabled();
  expect(screen.getByLabelText("标题")).toBeDisabled();
  expect(screen.getByLabelText("标题")).toHaveValue("不变的标题");
  expect(screen.getByLabelText("原文")).toHaveValue("原始内容");
  fireEvent.click(screen.getByRole("button", { name: "使用同一请求重试" }));
  await waitFor(() => expect(mocks.launch).toHaveBeenCalledTimes(2));
  expect(mocks.launch.mock.calls[0][0]).toEqual(mocks.launch.mock.calls[1][0]);
});
it("retains an unapplied expert draft through ordinary mode and requires applying it", async () => {
  const view = render(<Page />);
  await prepare();
  expect(screen.queryByRole("button", { name: "核对连接与本次设置" })).not.toBeInTheDocument();
  mocks.expert = true;
  view.rerender(<Page />);
  fireEvent.mouseDown(screen.getByRole("tab", { name: "Advanced JSON" }), { button: 0, ctrlKey: false });
  fireEvent.change(screen.getByLabelText("Parameters JSON"), {
    target: { value: '{"title":"draft"' },
  });
  mocks.expert = false;
  view.rerender(<Page />);
  expect(screen.getByLabelText("任务输入 JSON")).toHaveValue(
    '{"title":"draft"',
  );
  expect(
    screen.getByRole("button", { name: "核对连接与本次设置" }),
  ).toBeDisabled();
  mocks.expert = true;
  view.rerender(<Page />);
  expect(screen.getByLabelText("Parameters JSON")).toHaveValue(
    '{"title":"draft"',
  );
});
it("lets an explicit binding rejection be repaired and prepared again", async () => {
  mocks.launch.mockRejectedValue(
    new ApiRequestError({
      status: 409,
      code: "binding_changed",
      message: "Connections changed",
      details: [],
    }),
  );
  render(<Page />);
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "开始任务" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "核对连接与本次设置" }),
    ).toBeEnabled(),
  );
  expect(screen.getByLabelText("标题")).toBeEnabled();
  expect(
    screen.queryByRole("button", { name: "使用同一请求重试" }),
  ).not.toBeInTheDocument();
});

it("preserves explicit false and omitted schema/2 defaults when editing and saving a preset", async () => {
  mocks.schema = {type:"object",properties:{title:{type:"string",title:"标题"},includeRisk:{type:"boolean","x-signaldeck-schema":"signaldeck.schema/2",default:true},reportId:{type:"string","x-signaldeck-schema":"signaldeck.schema/2",default:"suggestion"}},required:["title","includeRisk"]};
  mocks.preset = {id:`exact-${mocks.hash}`,name:"Explicit inputs",packageKey:"research_notes",workflowKey:"capture",packageHash:`test-${mocks.hash}`,parameters:{title:"old",includeRisk:false},hasParameters:true,isFavorite:false,isPinned:false,currentPackageHash:`test-${mocks.hash}`,needsRevalidation:false,validationStatus:"valid",validationErrors:[]};
  render(<Page path={`/tasks/new?presetId=${mocks.preset.id}`} />);
  fireEvent.change(screen.getByLabelText("标题"),{target:{value:"edited"}});
  fireEvent.click(screen.getByText("保存常用输入或收藏任务（可选）"));
  fireEvent.click(screen.getByRole("button",{name:"更新此配置"}));
  await waitFor(()=>expect(mocks.save).toHaveBeenCalledTimes(1));
  expect(mocks.save.mock.calls[0][0].parameters).toEqual({title:"edited",includeRisk:false});
  await waitFor(()=>expect(mocks.prepare).toHaveBeenCalled());
  expect(mocks.prepare.mock.calls.at(-1)![0].parameters).toEqual({title:"edited",includeRisk:false});
});

it("commits pending identity before launch and restores it after a lost response in a new editor", async () => {
  let stored: Record<string, unknown> | undefined;
  mocks.saveDraft.mockImplementation(async (input) => {
    stored = { ...input, revision: input.revision + 1, workflow: { name: "Recovered", inputSchema: { type: "object", properties: { title: { type: "string", title: "标题" }, text: { type: "string", title: "原文" } }, required: ["title", "text"] } } };
    mocks.getDraft.mockResolvedValue(stored);
    return stored;
  });
  mocks.launch.mockImplementation(async () => {
    expect(stored?.pending).toBe(true);
    throw new Error("Response lost");
  });
  const first = render(<Page />);
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "开始任务" }));
  await waitFor(() => expect(mocks.launch).toHaveBeenCalledTimes(1));
  const original = mocks.launch.mock.calls[0][0];
  await waitFor(() => expect(screen.getByLabelText("Current route").textContent).toBe(`/tasks/new?draftId=${stored!.id}`));
  const refreshPath = screen.getByLabelText("Current route").textContent!;
  first.unmount();
  mocks.getDraft.mockResolvedValue(stored);
  render(<Page path={refreshPath} />);
  const retry = await screen.findByRole("button", { name: "使用同一请求重试" });
  expect(screen.getByLabelText("标题")).toBeDisabled();
  expect(screen.getByRole("button", { name: "删除草稿" })).toBeDisabled();
  fireEvent.click(retry);
  await waitFor(() => expect(mocks.launch).toHaveBeenCalledTimes(2));
  expect(mocks.launch.mock.calls[1][0]).toEqual(original);
});

it("does not send a launch if the pending draft cannot be persisted", async () => {
  mocks.saveDraft.mockRejectedValue(new Error("Draft response lost"));
  render(<Page />);
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "开始任务" }));
  await waitFor(() => expect(mocks.saveDraft).toHaveBeenCalledTimes(1));
  expect(mocks.launch).not.toHaveBeenCalled();
  expect(screen.getByLabelText("标题")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "使用同一请求重试" }));
  await waitFor(() => expect(mocks.saveDraft).toHaveBeenCalledTimes(2));
  expect(mocks.saveDraft.mock.calls[0][0]).toEqual(mocks.saveDraft.mock.calls[1][0]);
});

it("restores an unfinished draft with its frozen schema and saves invalid text without launching", async () => {
  mocks.getDraft.mockResolvedValue({
    id: `unfinished-${mocks.hash}`, revision: 3, name: "继续填写", packageKey: "research_notes", workflowKey: "capture", packageHash: "old-revision",
    hasParameters: true, parameters: { renamed: null }, jsonText: '{"renamed": [', launchId: "not-submitted", pending: false,
    needsRevalidation: true, workflow: { name: "Old definition", inputSchema: { type: "object", properties: { renamed: { type: ["string", "null"] } } } },
  });
  render(<Page path={`/tasks/new?draftId=unfinished-${mocks.hash}`} />);
  expect(await screen.findByLabelText("任务输入 JSON")).toHaveValue('{"renamed": [');
  expect(screen.getByRole("button", { name: "开始任务" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "保存草稿" }));
  await waitFor(() => expect(mocks.saveDraft).toHaveBeenCalledTimes(1));
  expect(mocks.saveDraft.mock.calls[0][0]).toMatchObject({ parameters: { renamed: null }, jsonText: '{"renamed": [', packageHash: "old-revision", revision: 3 });
  expect(mocks.launch).not.toHaveBeenCalled();
});

it("locks submission throughout pending persistence and keeps the lock across the recovery URL change", async () => {
  let finishSave!: () => void;
  let failLaunch!: (error: Error) => void;
  const normalSave = mocks.saveDraft.getMockImplementation()!;
  mocks.saveDraft.mockImplementation(async (input) => {
    await new Promise<void>(resolve => { finishSave = resolve; });
    return normalSave(input);
  });
  mocks.launch.mockImplementation(() => new Promise((_resolve, reject) => { failLaunch = reject; }));
  render(<Page />);
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "开始任务" }));
  const saving = await screen.findByRole("button", { name: "正在保存启动请求…" });
  expect(saving).toBeDisabled();
  expect(screen.getByRole("button", { name: "保存草稿" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "使用同一请求重试" })).not.toBeInTheDocument();
  fireEvent.click(saving);
  expect(mocks.saveDraft).toHaveBeenCalledTimes(1);
  expect(mocks.launch).not.toHaveBeenCalled();
  finishSave();
  await waitFor(() => expect(mocks.launch).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(screen.getByLabelText("Current route").textContent).toContain("?draftId="));
  expect(screen.getByRole("button", { name: "正在提交…" })).toBeDisabled();
  expect(screen.queryByRole("button", { name: "使用同一请求重试" })).not.toBeInTheDocument();
  failLaunch(new Error("Response lost"));
  await waitFor(() => expect(screen.getByRole("button", { name: "使用同一请求重试" })).toBeEnabled());
});
