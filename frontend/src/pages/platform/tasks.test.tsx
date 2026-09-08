import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, it, vi } from "vitest";
import { TaskPage } from "./tasks";
import { ApiRequestError } from "@/lib/api-client";
import type { ReuseInput, TaskPreset } from "@/lib/types/task-experience";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
const mocks = vi.hoisted(() => ({
  prepare: vi.fn(),
  launch: vi.fn(),
  save: vi.fn(),
  expert: false,
  hash: 0,
  historical: undefined as ReuseInput | undefined,
  preset: undefined as TaskPreset | undefined,
  schema: undefined as JsonObject | undefined,
}));
vi.mock("@/hooks/use-display-mode", () => ({
  useDisplayMode: () => ({ expert: mocks.expert }),
}));
vi.mock("@/hooks/use-workflow-platform", () => ({
  usePackages: () => ({
    data: {
      items: [
        {
          key: "research_notes",
          packageHash: `test-${mocks.hash}`,
          definition: {
            workflows: {
              capture: {
                inputSchema: mocks.schema ?? {
                  type: "object",
                  properties: {
                    title: { type: "string", minLength: 1 },
                    text: { type: "string" },
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
function Page({ path = "/tasks/new?packageKey=research_notes&workflowKey=capture" }: { path?: string }) {
  const [client] = useState(() => new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } }));
  return (
    <QueryClientProvider client={client}>
    <MemoryRouter
      initialEntries={[
        path,
      ]}
    >
      <TaskPage />
    </MemoryRouter>
    </QueryClientProvider>
  );
}
beforeEach(() => {
  mocks.hash++;
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
it.each([
  [null, { type: ["string", "null"], default: "authored default" }],
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
    sourceRunId: "nullable-original",
    packageKey: "nullable-task",
    workflowKey: "main",
    packageHash: "nullable-hash",
    parameters: null,
    inputSchema: { type: ["string", "null"], default: "authored default" },
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
  expect(mocks.launch).not.toHaveBeenCalled();
  fireEvent.click(start);
  await waitFor(() => expect(mocks.launch).toHaveBeenCalledTimes(1));
  expect(mocks.launch.mock.calls[0][0].parameters).toEqual({ title: "一次开始", text: "保留业务原文" });
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
it("retries uncertain submissions with the same identity and prevents editing the submitted input", async () => {
  mocks.launch.mockRejectedValue(new TypeError("Network response lost"));
  render(<Page />);
  await prepare();
  fireEvent.click(screen.getByRole("button", { name: "开始任务" }));
  await screen.findByRole("button", { name: "使用同一请求重试" });
  expect(screen.getByLabelText("标题")).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "使用同一请求重试" }));
  await waitFor(() => expect(mocks.launch).toHaveBeenCalledTimes(2));
  expect(mocks.launch.mock.calls[0][0]).toEqual(mocks.launch.mock.calls[1][0]);
});
it("retains an unapplied expert draft through ordinary mode and requires applying it", async () => {
  mocks.expert = true;
  const view = render(<Page />);
  fireEvent.click(screen.getByRole("tab", { name: "Advanced JSON" }));
  fireEvent.change(screen.getByLabelText("Parameters JSON"), {
    target: { value: '{"title":"draft"' },
  });
  mocks.expert = false;
  view.rerender(<Page />);
  expect(screen.getByLabelText("Parameters JSON")).toHaveValue(
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
