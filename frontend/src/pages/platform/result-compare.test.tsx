import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ResultComparePage } from "./result-compare";
import type { RunResult } from "@/lib/types/result";
const base: RunResult = {
  runId: "left", title: "正文", status: "succeeded", contentStatus: "available", body: "same body", receipt: null,
  dataTime: null, createdAt: "2026-09-10T00:00:00Z", finishedAt: "2026-09-10T00:01:00Z", cancelRequestedAt: null, origin: { kind: "manual" }, sources: ["source"], missing: [], attachments: [], unknownEvidenceIds: [], freshness: [], errorCode: null,
};
function mount(overrides: Partial<RunResult> = {}, search = "left=left&right=right&leftSection=body&rightSection=body") {
  const fetch = vi.fn(async (url: string) => {
    if (url.includes("/runs?")) return new Response(JSON.stringify({ items: [{ id: "right", title: "最近结果", status: "succeeded", createdAt: base.createdAt }], total: 1, limit: 10, offset: 0, snapshotAt: base.createdAt }), { headers: { "content-type": "application/json" } });
    if (url.includes("/artifacts/")) return new Response("large artifact text");
    const id = url.includes("/left/") ? "left" : "right";
    return new Response(JSON.stringify(url.endsWith("/reuse") ? { sourceRunId: id, packageKey: "p", workflowKey: "w", packageHash: `hash-${id}`, parameters: { arbitrary: id }, inputSchema: {} }
      : { ...base, runId: id, ...(id === "right" ? overrides : {}) }), { headers: { "content-type": "application/json" } });
  });
  vi.stubGlobal("fetch", fetch);
  const router = createMemoryRouter([{ path: "/runs/compare", element: <ResultComparePage /> }], { initialEntries: [`/runs/compare?${search}`] });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RouterProvider router={router} /></QueryClientProvider>);
  return { fetch, router };
}
afterEach(() => vi.unstubAllGlobals());
it("retains different run identities, revisions, input and unknown status with identical text", async () => {
  const { router } = mount({ status: "cancelled", contentStatus: "unknown", cancelRequestedAt: "2026-09-10T00:00:30Z" });
  expect(await screen.findByText(/所选正文相同/)).toBeVisible();
  expect(await screen.findByText(/hash-left/)).toBeVisible();
  expect(await screen.findByText(/hash-right/)).toBeVisible();
  expect(screen.getByText(/输入摘要：.*right/)).toBeVisible();
  expect(screen.getByText(/保存状态待核实；当前仅比较/)).toBeVisible();
  expect(screen.getByText(/已请求取消；已确认的外部操作仍会保留/)).toBeVisible();
  expect(router.state.location.search).toContain("left=left");
  expect(router.state.location.search).toContain("right=right");
});
it("requires explicit attachment reading even with a fixed selection URL", async () => {
  const { fetch } = mount({ body: null, attachments: [{ kind: "artifact", label: "大正文", reference: { digest: `sha256:${"a".repeat(64)}`, mediaType: "text/plain", sizeBytes: 100000 } }] }, "left=left&right=right&leftSection=body&rightSection=artifact:0:0");
  const read = await screen.findByRole("button", { name: "读取右侧所选附件" });
  expect(fetch.mock.calls.some(([url]) => url.includes("/artifacts/"))).toBe(false);
  fireEvent.click(read);
  await waitFor(() => expect(within(screen.getByRole("region", { name: "右侧结果" })).getByText("large artifact text")).toBeVisible());
  expect(screen.getByText("左侧删除")).toBeVisible();
  expect(screen.getByText("右侧新增")).toBeVisible();
});
it("keeps empty results honest and uses explicit generic JSON section selection", async () => {
  const { router } = mount({ body: null, sections: [{ kind: "value", label: "任意输出", value: { alien: "# literal" } }] }, "left=left&right=right");
  const select = await screen.findByRole("combobox", { name: "右侧确认内容" });
  fireEvent.keyDown(select, { key: "ArrowDown" });
  fireEvent.click(await screen.findByRole("option", { name: "任意输出" }));
  expect(router.state.location.search).toContain("rightSection=section%3A0");
  expect(screen.getByText(/"alien": "# literal"/)).toBeVisible();
  expect(screen.queryByRole("heading", { name: "literal" })).not.toBeInTheDocument();
  expect(screen.getByText(/请选择两侧确认内容/)).toBeVisible();
});

it("selects a known result from server history without requiring its ID to be remembered", async () => {
  const { router } = mount({}, "left=left");
  fireEvent.click(screen.getByRole("button", { name: "从结果记录选择" }));
  fireEvent.click(await screen.findByRole("button", { name: "将 right 选为右侧" }));
  expect(screen.getByLabelText("右侧运行 ID")).toHaveValue("right");
  fireEvent.click(screen.getByRole("button", { name: "固定两次结果" }));
  expect(router.state.location.search).toBe("?left=left&right=right");
});
