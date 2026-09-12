import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { ResultMetadataControls } from "./result-metadata";
const initial = { runId: "r1", revision: 0, isFavorite: false, isRead: false, note: "", updatedAt: null };
function response(value: unknown, status = 200) { return new Response(JSON.stringify(value), { status, headers: { "content-type": "application/json" } }); }
function mount() {
  return render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><ResultMetadataControls runId="r1" /></QueryClientProvider>);
}
afterEach(() => vi.unstubAllGlobals());
it("reads without a write and submits only the explicit metadata field", async () => {
  let current = { ...initial };
  const patches: object[] = [];
  vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => {
    if (options?.method === "PATCH") { const patch = JSON.parse(options.body as string); patches.push(patch); current = { ...current, isFavorite: patch.isFavorite, revision: 1 }; }
    return response(current);
  }));
  mount();
  expect(await screen.findByRole("button", { name: "收藏结果" })).toBeEnabled();
  expect(patches).toEqual([]);
  fireEvent.click(screen.getByRole("button", { name: "收藏结果" }));
  expect(await screen.findByRole("button", { name: "取消收藏" })).toBeEnabled();
  expect(patches).toEqual([{ expectedRevision: 0, isFavorite: true }]);
});
it("retains a conflicting note draft and requires review of the newer version", async () => {
  let current = { ...initial };
  const patches: { expectedRevision: number; note: string }[] = [];
  vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => {
    if (options?.method === "PATCH") {
      const patch = JSON.parse(options.body as string); patches.push(patch);
      if (patches.length === 1) { current = { ...current, revision: 1, note: "另一窗口的备注" }; return response({ code: "result_metadata_conflict", message: "changed", details: [] }, 409); }
      current = { ...current, revision: 2, note: patch.note };
    }
    return response(current);
  }));
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "编辑个人备注" }));
  fireEvent.change(screen.getByRole("textbox", { name: "个人备注" }), { target: { value: "我的草稿" } });
  fireEvent.click(screen.getByRole("button", { name: "保存个人备注" }));
  expect(await screen.findByText("保存版本已变化")).toBeVisible();
  expect(screen.getByRole("textbox", { name: "个人备注" })).toHaveValue("我的草稿");
  expect(screen.getByRole("button", { name: "保存个人备注" })).toBeDisabled();
  expect(screen.getByText("最新已保存备注：另一窗口的备注")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "已核对，保留草稿并使用最新版本" }));
  fireEvent.click(screen.getByRole("button", { name: "保存个人备注" }));
  await waitFor(() => expect(patches).toHaveLength(2));
  expect(patches[1]).toEqual({ expectedRevision: 1, note: "我的草稿" });
});


it("retains an unsaved note across navigation and warns before refresh without browser persistence", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => response(initial)));
  const first = mount();
  fireEvent.click(await screen.findByRole("button", { name: "编辑个人备注" }));
  fireEvent.change(screen.getByRole("textbox", { name: "个人备注" }), { target: { value: "请保留我的备注草稿" } });
  first.unmount();
  mount();
  expect(await screen.findByRole("textbox", { name: "个人备注" })).toHaveValue("请保留我的备注草稿");
  const refresh = new Event("beforeunload", { cancelable: true });
  expect(window.dispatchEvent(refresh)).toBe(false);
  expect(JSON.stringify({ ...sessionStorage, ...localStorage })).not.toContain("请保留我的备注草稿");
  fireEvent.click(screen.getByRole("button", { name: "取消编辑" }));
  expect(window.dispatchEvent(new Event("beforeunload", { cancelable: true }))).toBe(true);
});
