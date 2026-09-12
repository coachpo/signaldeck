import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";
import { TaskConnections } from "./task-connections";
import type { ConnectionPreset, Requirement } from "@/lib/types/task-experience";
const presetsQuery = vi.hoisted(() => vi.fn());
const resourcesQuery = vi.hoisted(() => vi.fn());
const save = vi.hoisted(() => vi.fn().mockResolvedValue({}));
vi.mock("@/hooks/use-workflow-platform", () => ({
  usePlatformMutations: () => ({ saveResource: { mutateAsync: save } }),
  useResources: resourcesQuery,
  usePlugins: () => ({ data: { items: [] }, refetch: vi.fn() }),
}));
vi.mock("@/hooks/use-task-experience", () => ({ useConnectionPresets: presetsQuery }));
beforeEach(() => {
  save.mockClear();
  presetsQuery.mockReturnValue({ data: { items: [] }, isPending: false, refetch: vi.fn() });
  resourcesQuery.mockReturnValue({ data: { items: [] }, refetch: vi.fn() });
});
const modelConfig = { name: "研究服务", baseUrl: "http://localhost/v1", modelId: "local", apiStyle: "chat_completions", timeoutSeconds: 60 };
function requirement(id: string, configured = false): Requirement {
  return { id, kind: "model", name: "研究服务", configured, hasCredentials: configured, config: configured ? modelConfig : {}, observation: "not_observed" };
}
function content(item: Requirement, done = vi.fn()) { return <MemoryRouter><TaskConnections requirements={[item]} onSaved={done} /></MemoryRouter>; }
async function choose(name: string) {
  fireEvent.keyDown(screen.getByRole("combobox", { name: "连接来源" }), { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name }));
}
it("requires confirmation, preserves configuration, clears entered secrets and omits blank credentials", async () => {
  const done = vi.fn();
  render(content(requirement("confirmation-model", true), done));
  fireEvent.click(screen.getByText("研究服务 · 管理连接"));
  expect(screen.getByRole("button", { name: "保存连接" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("服务密钥"), { target: { value: "session-secret" } });
  fireEvent.click(screen.getByLabelText("确认使用以上服务、账户、业务范围及保存位置"));
  fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
  await waitFor(() => expect(done).toHaveBeenCalledOnce());
  expect(screen.getByLabelText("服务密钥")).toHaveValue("");
  expect(save).toHaveBeenCalledWith({ resourceId: "confirmation-model", kind: "model", config: modelConfig, credentials: { apiKey: "session-secret" } });
  fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
  expect(save.mock.calls[1][0]).not.toHaveProperty("credentials");
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain("session-secret");
});
it("allows a missing model to be connected with an ordinary address and password form", async () => {
  const done = vi.fn();
  render(content(requirement("new-inline-model"), done));
  fireEvent.change(screen.getByLabelText("服务地址"), { target: { value: "http://192.168.1.222:8088/v1/chat/completions" } });
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "glm-5.3-flash" } });
  fireEvent.change(screen.getByLabelText("服务密钥"), { target: { value: "sk-dummy" } });
  fireEvent.click(screen.getByLabelText("确认使用以上服务、账户、业务范围及保存位置"));
  fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
  await waitFor(() => expect(done).toHaveBeenCalledOnce());
  expect(save.mock.calls[0][0]).toMatchObject({ resourceId: "new-inline-model", config: { baseUrl: "http://192.168.1.222:8088/v1", modelId: "glm-5.3-flash" }, credentials: { apiKey: "sk-dummy" } });
  expect(screen.queryByText(/new-inline-model|JSON|apiStyle|resourceId/)).not.toBeInTheDocument();
});
it("keeps inputs and gives actionable local validation when the address is wrong", async () => {
  render(content(requirement("invalid-model")));
  fireEvent.change(screen.getByLabelText("服务地址"), { target: { value: "bad address" } });
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "my-model" } });
  fireEvent.click(screen.getByLabelText("确认使用以上服务、账户、业务范围及保存位置"));
  fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("请填写完整的服务地址");
  expect(screen.getByLabelText("模型名称")).toHaveValue("my-model");
  expect(save).not.toHaveBeenCalled();
});
it("distinguishes loading and preset failures while preserving entered credentials", async () => {
  const candidate: ConnectionPreset = { id: "preset", resourceId: "preset-model", kind: "model", name: "可选研究服务", description: "", config: modelConfig, credentialFields: [{ key: "apiKey", label: "服务密钥", required: true }] };
  const done = vi.fn();
  presetsQuery.mockReturnValue({ isPending: true, refetch: vi.fn() });
  const view = render(content(requirement("preset-model"), done));
  expect(screen.getByText("正在查找可用连接…")).toBeVisible();
  presetsQuery.mockReturnValue({ data: { items: [candidate] }, isPending: false });
  view.rerender(content(requirement("preset-model"), done));
  expect(screen.getByText("请选择一个连接，或填写自己的服务。")).toBeVisible();
  await choose("可选研究服务");
  fireEvent.change(screen.getByLabelText("服务密钥（必填）"), { target: { value: "private-draft" } });
  presetsQuery.mockReturnValue({ data: { items: [candidate] }, isPending: false, error: new Error("Internal DB failure"), refetch: vi.fn() });
  view.rerender(content(requirement("preset-model"), done));
  expect(screen.getByText(/暂时无法更新连接选项/)).toBeVisible();
  expect(screen.getByLabelText("服务密钥（必填）")).toHaveValue("private-draft");
  expect(screen.queryByText(/Internal DB failure/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByLabelText("确认使用以上服务、账户、业务范围及保存位置"));
  fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
  await waitFor(() => expect(done).toHaveBeenCalledOnce());
});
it("copies saved public connection settings without implying credentials were copied", async () => {
  resourcesQuery.mockReturnValue({ data: { items: [{ resourceId: "other-model", kind: "model", config: { ...modelConfig, name: "已有研究模型" }, hasCredentials: true }] } });
  render(content(requirement("copy-model")));
  await choose("复制 已有研究模型 的设置");
  expect(screen.getByLabelText("服务地址")).toHaveValue(modelConfig.baseUrl);
  expect(screen.getByLabelText("服务密钥")).toHaveValue("");
  expect(screen.getByText(/密钥不会从其他连接复制/)).toBeVisible();
  expect(save).not.toHaveBeenCalled();
});
it("retains the public draft across page remounts without browser storage", () => {
  const item = requirement("retained-model");
  const view = render(content(item));
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "unfinished-analysis" } });
  view.unmount();
  render(content(item));
  expect(screen.getByLabelText("模型名称")).toHaveValue("unfinished-analysis");
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain("unfinished-analysis");
});
