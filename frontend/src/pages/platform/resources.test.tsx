import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it, vi } from "vitest";
import type { Resource, ResourceWrite } from "@/lib/types/workflow-platform";
import { ResourcesPage } from "./resources";
const state = vi.hoisted(() => ({ items: [] as Resource[], save: vi.fn() }));
vi.mock("@/hooks/use-workflow-platform", () => ({
  useResources: () => ({ data: { items: state.items }, refetch: vi.fn() }),
  usePlugins: () => ({ data: { items: [] }, refetch: vi.fn() }),
  usePlatformMutations: () => ({ saveResource: { mutateAsync: state.save } }),
}));
it("creates a named service through a form, manages its identity and clears credentials after save", async () => {
  state.save.mockImplementation(async (input: ResourceWrite) => {
    const saved: Resource = { resourceId: input.resourceId, kind: input.kind, config: input.config, credentialRevision: "internal-revision", hasCredentials: true };
    state.items.push(saved); return saved;
  });
  render(<MemoryRouter><ResourcesPage /></MemoryRouter>);
  fireEvent.change(screen.getByLabelText("连接名称"), { target: { value: "我的分析模型" } });
  fireEvent.change(screen.getByLabelText("服务地址"), { target: { value: "http://localhost:18081/v1/chat/completions" } });
  fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "analysis-model" } });
  fireEvent.change(screen.getByLabelText("服务密钥"), { target: { value: "private-value" } });
  fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
  await waitFor(() => expect(state.save).toHaveBeenCalledOnce());
  expect(await screen.findByText(/已保存“我的分析模型”/)).toBeVisible();
  expect(screen.getByLabelText("服务密钥")).toHaveValue("");
  const payload = state.save.mock.calls[0][0];
  expect(payload.resourceId).toMatch(/^connection-/);
  expect(payload.config.baseUrl).toBe("http://localhost:18081/v1");
  expect(payload.credentials).toEqual({ apiKey: "private-value" });
  expect(document.body.textContent).not.toContain(payload.resourceId);
  expect(document.body.textContent).not.toMatch(/internal-revision|Resource ID|JSON/);
  expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain("private-value");
});
