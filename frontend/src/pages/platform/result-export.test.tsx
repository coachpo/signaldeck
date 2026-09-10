import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import type { RunResult } from "@/lib/types/result";
import { ResultExport } from "./result-export";
const result: RunResult = {
  runId: "one", title: "正文", status: "succeeded", contentStatus: "available", body: "# 确认正文", receipt: null,
  dataTime: null, createdAt: "2026-09-10T00:00:00Z", finishedAt: null, cancelRequestedAt: null, origin: { kind: "manual" }, sources: [], missing: [], attachments: [], unknownEvidenceIds: [], freshness: [], errorCode: null,
};
function mount(input = result) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<QueryClientProvider client={client}><ResultExport result={input} /></QueryClientProvider>);
}
afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks(); });
it("copies confirmed content and keeps clipboard failure recoverable", async () => {
  const writeText = vi.fn().mockRejectedValueOnce(new Error("denied")).mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "复制所选正文" }));
  expect(await screen.findByText(/复制失败/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "复制所选正文" }));
  expect(await screen.findByText("所选确认内容已复制。")).toBeVisible();
  expect(writeText.mock.calls[1][0]).toContain("# 确认正文");
});
it("reads selected artifacts only and blocks delivery until loaded, with retry", async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error("offline")).mockResolvedValue(new Response("artifact content"));
  vi.stubGlobal("fetch", fetch);
  mount({ ...result, attachments: [{ kind: "artifact", label: "大正文", reference: { digest: `sha256:${"a".repeat(64)}`, sizeBytes: 100000, mediaType: "text/plain" } }] });
  expect(fetch).not.toHaveBeenCalled();
  fireEvent.click(screen.getByText(/选择复制与导出的内容/));
  fireEvent.click(screen.getByLabelText(/读取并选入附件：大正文/));
  expect(screen.getByRole("button", { name: "导出 Markdown" })).toBeDisabled();
  expect(await screen.findByText(/附件读取失败/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "重试读取" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "导出 Markdown" })).toBeEnabled());
  expect(fetch).toHaveBeenCalledTimes(2);
});
it("reports failed downloads and allows retry", async () => {
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn().mockImplementation(() => { throw new Error("unavailable"); }) });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "导出 Markdown" }));
  expect(await screen.findByText(/导出失败/)).toBeVisible();
  expect(screen.getByRole("button", { name: "导出 Markdown" })).toBeEnabled();
});
it("does not offer export for unconfirmed empty output", () => {
  mount({ ...result, status: "failed", contentStatus: "not_available", body: null });
  expect(screen.getByRole("button", { name: "导出 Markdown" })).toBeDisabled();
  expect(screen.getByText(/尚无可复制或导出的确认正文/)).toBeVisible();
});

it("downloads a Markdown file containing provenance and confirmation status", async () => {
  const create = vi.fn().mockReturnValue("blob:result");
  const revoke = vi.fn();
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: revoke });
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function(this: HTMLAnchorElement) {
    expect(this.download).toBe("result-one.md");
  });
  mount();
  fireEvent.click(screen.getByRole("button", { name: "导出 Markdown" }));
  expect(await screen.findByText("已请求下载所选确认内容。")).toBeVisible();
  const file = create.mock.calls[0][0] as Blob;
  expect(file.type).toBe("text/markdown;charset=utf-8");
  expect(file.size).toBeGreaterThan(50);
  expect(click).toHaveBeenCalledOnce();
  expect(revoke).toHaveBeenCalledWith("blob:result");
});
