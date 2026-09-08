import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import { TaskConnections } from "./task-connections";
const save = vi.hoisted(() => vi.fn().mockResolvedValue({}));
vi.mock("@/hooks/use-workflow-platform", () => ({
  usePlatformMutations: () => ({ saveResource: { mutateAsync: save } }),
}));
vi.mock("@/hooks/use-task-experience", () => ({
  useConnectionPresets: () => ({ data: { items: [] } }),
}));
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
