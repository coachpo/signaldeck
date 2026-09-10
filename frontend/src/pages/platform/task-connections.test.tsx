import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";
import { TaskConnections } from "./task-connections";
import type { ConnectionPreset, Requirement } from "@/lib/types/task-experience";
const presetsQuery = vi.hoisted(() => vi.fn());
const save = vi.hoisted(() => vi.fn().mockResolvedValue({}));
vi.mock("@/hooks/use-workflow-platform", () => ({
  usePlatformMutations: () => ({ saveResource: { mutateAsync: save } }),
}));
vi.mock("@/hooks/use-task-experience", () => ({
  useConnectionPresets: presetsQuery,
}));
beforeEach(() => {
  save.mockClear();
  presetsQuery.mockReturnValue({ data: { items: [] }, isPending: false, error: null });
});
it("requires scope confirmation, preserves config, clears the secret and omits blank credentials", async () => {
  const done = vi.fn();
  render(
    <MemoryRouter>
      <TaskConnections
        requirements={[
          {
            id: "fixed-model",
            kind: "model",
            name: "研究服务",
            configured: true,
            hasCredentials: true,
            config: {
              name: "已配置服务",
              baseUrl: "http://localhost/v1",
              modelId: "local",
              apiStyle: "chat_completions",
            },
            observation: "not_observed",
          },
        ]}
        onSaved={done}
      />
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByText("研究服务 · 管理连接"));
  expect(screen.getByRole("button", { name: "保存连接" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("服务密钥"), {
    target: { value: "session-secret" },
  });
  fireEvent.click(
    screen.getByLabelText("确认使用以上服务、账户、业务范围及保存位置"),
  );
  fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
  await waitFor(() => expect(done).toHaveBeenCalled());
  expect(screen.getByLabelText("服务密钥")).toHaveValue("");
  expect(save.mock.calls[0][0]).toEqual({
    resourceId: "fixed-model",
    kind: "model",
    config: {
      name: "已配置服务",
      baseUrl: "http://localhost/v1",
      modelId: "local",
      apiStyle: "chat_completions",
    },
    credentials: { apiKey: "session-secret" },
  });
  fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
  expect(save.mock.calls[1][0]).not.toHaveProperty("credentials");
  expect(localStorage.getItem("session-secret")).toBeNull();
});

const missing: Requirement = {
  id: "fixed-model", kind: "model", name: "研究服务", configured: false,
  hasCredentials: false, config: {}, observation: "not_observed",
};
const candidate: ConnectionPreset = {
  id: "deployed", resourceId: "fixed-model", kind: "model", name: "可选研究服务",
  description: "部署方的连接", config: { modelId: "chosen-model", scope: "personal" },
  credentialFields: [{ key: "apiKey", label: "服务密钥", required: true }],
};
function missingConnection() {
  return <MemoryRouter><TaskConnections requirements={[missing]} onSaved={vi.fn()} /></MemoryRouter>;
}
it("distinguishes loading, failure, empty and awaiting explicit selection", () => {
  const refetch = vi.fn();
  presetsQuery.mockReturnValue({ isPending: true, refetch });
  const view = render(missingConnection());
  fireEvent.click(screen.getByText("研究服务 · 补齐连接"));
  expect(screen.getByText("正在加载部署方服务预设…")).toBeVisible();
  expect(screen.queryByText(/没有适用于此任务/)).not.toBeInTheDocument();
  presetsQuery.mockReturnValue({ isPending: false, error: new Error("预设不可用"), refetch });
  view.rerender(missingConnection());
  expect(screen.getByText(/服务预设加载失败/)).toBeVisible();
  expect(screen.queryByText(/正在加载/)).not.toBeInTheDocument();
  expect(screen.queryByText(/没有适用于此任务/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(refetch).toHaveBeenCalledOnce();
  presetsQuery.mockReturnValue({ data: { items: [] }, isPending: false });
  view.rerender(missingConnection());
  expect(screen.getByText(/没有适用于此任务/)).toBeVisible();
  presetsQuery.mockReturnValue({ data: { items: [candidate] }, isPending: false });
  view.rerender(missingConnection());
  expect(screen.getByText(/请选择部署方提供的服务/)).toBeVisible();
  expect(screen.queryByText(/没有适用于此任务/)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "保存连接" })).not.toBeInTheDocument();
  expect(save).not.toHaveBeenCalled();
});
it("shows selected configuration only after choice and preserves secret input through query errors", async () => {
  const done = vi.fn();
  presetsQuery.mockReturnValue({ data: { items: [candidate] }, isPending: false });
  const content = <MemoryRouter><TaskConnections requirements={[missing]} onSaved={done} /></MemoryRouter>;
  const view = render(content);
  fireEvent.click(screen.getByText("研究服务 · 补齐连接"));
  fireEvent.keyDown(screen.getByRole("combobox"), { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: "可选研究服务" }));
  expect(screen.queryByText(/请选择部署方提供的服务/)).not.toBeInTheDocument();
  expect(screen.getByText("chosen-model")).toBeVisible();
  fireEvent.change(screen.getByLabelText("服务密钥"), { target: { value: "new-secret" } });
  presetsQuery.mockReturnValue({ data: { items: [candidate] }, error: new Error("暂时无法更新"), isPending: false });
  view.rerender(<MemoryRouter><TaskConnections requirements={[missing]} onSaved={done} /></MemoryRouter>);
  expect(screen.getByLabelText("服务密钥")).toHaveValue("new-secret");
  expect(screen.getByRole("button", { name: "保存连接" })).toBeDisabled();
  fireEvent.click(screen.getByLabelText("确认使用以上服务、账户、业务范围及保存位置"));
  fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
  await waitFor(() => expect(done).toHaveBeenCalledOnce());
  expect(save).toHaveBeenCalledWith({ resourceId: missing.id, kind: "model", config: candidate.config, credentials: { apiKey: "new-secret" } });
  expect(screen.getByLabelText("服务密钥")).toHaveValue("");
});

it("shows the configured model observation with safe guidance and evidence", () => {
  render(<MemoryRouter><TaskConnections requirements={[{
    ...missing, configured: true, config: candidate.config,
    modelObservation: {
      status: "failed", observedAt: "2026-09-10T00:00:00Z",
      errorCode: "model_http_error", errorCategory: "quota",
      runId: "model-run", evidenceId: "model-node",
    },
  }]} onSaved={vi.fn()} /></MemoryRouter>);
  fireEvent.click(screen.getByText("研究服务 · 管理连接"));
  expect(screen.getByText("当前已保存连接的调用观测")).toBeVisible();
  expect(screen.getByText(/最近调用失败/)).toBeVisible();
  expect(screen.getByText(/模型服务额度不足/)).toBeVisible();
  expect(screen.getByRole("link", { name: "查看最近调用证据" })).toHaveAttribute("href", "/runs/model-run?tab=evidence&target=model-node");
  expect(save).not.toHaveBeenCalled();
});
it("does not imply a configured model without observations is online", () => {
  render(<MemoryRouter><TaskConnections requirements={[{
    ...missing, configured: true, config: candidate.config,
  }]} onSaved={vi.fn()} /></MemoryRouter>);
  fireEvent.click(screen.getByText("研究服务 · 管理连接"));
  expect(screen.getByText("当前连接配置尚无调用观测")).toBeVisible();
  expect(screen.queryByRole("link", { name: "查看最近调用证据" })).not.toBeInTheDocument();
});
