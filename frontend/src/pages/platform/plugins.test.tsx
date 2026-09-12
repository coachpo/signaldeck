import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";
import { PluginsPage } from "./plugins";
import type { PluginRelease } from "@/lib/types/workflow-platform";
const save = vi.hoisted(() => vi.fn().mockResolvedValue({}));
const query = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-workflow-platform", () => ({
  usePlugins: query,
  usePlatformMutations: () => ({ savePlugin: { mutateAsync: save }, enablePlugin: { mutate: vi.fn() } }),
}));
const release: PluginRelease = { pluginId: "private/service", releaseId: "internal-version", artifactDigest: "hidden-artifact", contractDigest: "hidden-contract", endpoint: "http://localhost:8020/mcp/", protocolVersion: "2025-11-25", configSchema: { type: "object", title: "资料服务" }, tools: [{ toolId: "private/service/store", inputSchema: { type: "object", title: "保存资料" }, effect: "write" }], supportsOperationQuery: true, supportsOperationDeduplication: true };
beforeEach(() => { save.mockClear(); query.mockReturnValue({ data: { items: [] }, refetch: vi.fn() }); });
function selectFile(text: string) { fireEvent.change(screen.getByLabelText("选择安装文件"), { target: { files: [{ name: "service-install.json", text: () => Promise.resolve(text) }] } }); }
it("imports an installation file, reviews capabilities and waits for explicit confirmation before registration", async () => {
  render(<MemoryRouter><PluginsPage /></MemoryRouter>);
  selectFile(JSON.stringify({ release }));
  expect(await screen.findByText("资料服务")).toBeVisible();
  expect(screen.getByText("保存资料")).toBeVisible();
  expect(screen.getByText("可保存或修改资料")).toBeVisible();
  expect(screen.getByRole("button", { name: "添加服务" })).toBeDisabled();
  expect(document.body.textContent).not.toMatch(/private\/service|hidden-artifact|internal-version|2025-11-25|supportsOperation/);
  fireEvent.click(screen.getByLabelText("我已核对服务来源和上述读取、保存能力"));
  fireEvent.click(screen.getByRole("button", { name: "添加服务" }));
  await waitFor(() => expect(save).toHaveBeenCalledWith({ release, enabled: false }));
  expect(await screen.findByRole("status")).toHaveTextContent("已添加");
});
it("keeps a valid installation draft after an invalid file and provides a readable recovery", async () => {
  render(<MemoryRouter><PluginsPage /></MemoryRouter>);
  selectFile(JSON.stringify(release));
  expect(await screen.findByText("保存资料")).toBeVisible();
  selectFile('{"broken":');
  expect(await screen.findByText(/请选择服务提供方导出的完整连接文件/)).toBeVisible();
  expect(screen.getByText("保存资料")).toBeVisible();
  expect(save).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "放弃本次选择" }));
});
