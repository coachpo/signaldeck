import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { runFixture } from "./fixtures";
import { artifactPresentation, projectedArtifactText } from "./result-artifact-presentation";
import { ResultAttachmentView } from "./result-content";
import { ResultExport } from "./result-export";
import { confirmedContents, readableContent } from "./result-delivery";
import type { ResultAttachment, RunResult } from "@/lib/types/result";
const ref = { digest: `sha256:${"a".repeat(64)}`, sizeBytes: 100000, mediaType: "application/json" };
const stored = JSON.stringify({ renamedBody: "# 原文\n\nUser code: schema.operationId = 42;", operationId: "internal-operation", storedPath: "/private/runtime/data" });
const artifactQuery = vi.hoisted(() => vi.fn());
const download = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const read = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-workflow-platform", () => ({ useArtifact: artifactQuery }));
vi.mock("@/lib/api/workflow-platform", () => ({ workflowPlatformApi: { downloadArtifact: download, artifact: read } }));
const attachment: ResultAttachment = { kind: "artifact", label: "正文附件", evidenceId: "node-1", nodeId: "answer", reference: { $artifact: ref } };
function fixture() {
  const run = structuredClone(runFixture);
  run.spec.definition.workflows.main.presentation = { version: "signaldeck.presentation/1", sections: [
    { kind: "markdown", label: "正文", ref: "nodes.answer.output.renamedBody" },
    { kind: "receipt", label: "保存确认", ref: "nodes.answer.output" },
  ] };
  run.evidence[0].output = { $artifact: ref };
  run.evidence[0].status = "succeeded";
  return run;
}
const result: RunResult = { runId: "run-1", title: "正文", status: "succeeded", contentStatus: "available", body: null, receipt: null, dataTime: null, createdAt: "2026-09-12T00:00:00Z", finishedAt: null, cancelRequestedAt: null, origin: { kind: "manual" }, sources: [], missing: [], attachments: [attachment], unknownEvidenceIds: [], freshness: [], errorCode: null };
afterEach(() => { vi.clearAllMocks(); });
it("reads a large response through the frozen declared selector without exposing its envelope", async () => {
  const presentation = artifactPresentation(fixture(), attachment, ref.digest);
  artifactQuery.mockReturnValue({ data: stored });
  render(<ResultAttachmentView attachment={attachment} presentation={presentation} />);
  fireEvent.click(screen.getByRole("button", { name: "阅读附件正文" }));
  expect(screen.getByRole("heading", { name: "原文" })).toBeVisible();
  expect(screen.getByText("User code: schema.operationId = 42;")).toBeVisible();
  expect(screen.getByText("此项保存已确认。")).toBeVisible();
  expect(screen.queryByText(/internal-operation|private\/runtime/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "下载原始附件" }));
  expect(download).toHaveBeenCalledWith(ref.digest, "正文附件");
});
it("exports only declared large content and preserves the user's original code", async () => {
  read.mockResolvedValue(stored);
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><ResultExport result={result} run={fixture()} /></QueryClientProvider>);
  fireEvent.click(screen.getByText(/选择复制与导出的内容/));
  fireEvent.click(screen.getByLabelText(/读取并选入附件：正文附件/));
  expect(read).toHaveBeenCalledWith(ref.digest);
  await vi.waitFor(() => expect(screen.getByRole("button", { name: "复制所选正文" })).toBeEnabled());
  fireEvent.click(screen.getByRole("button", { name: "复制所选正文" }));
  await screen.findByText("所选确认内容已复制。");
  const text = writeText.mock.calls[0][0];
  expect(text).toContain("User code: schema.operationId = 42;");
  expect(text).not.toMatch(/internal-operation|private\/runtime|sha256:/);
});
it("does not interpret a tool envelope with selectors belonging to a differently mapped node", () => {
  const run = fixture();
  const toolAttachment = { ...attachment, evidenceId: "tool-1" };
  run.evidence[2].output = { $artifact: ref };
  const presentation = artifactPresentation(run, toolAttachment, ref.digest);
  expect(presentation?.unavailable).toBe(true);
  render(<ResultAttachmentView attachment={toolAttachment} presentation={presentation} />);
  expect(screen.getByText(/附件正文暂时无法展开/)).toBeVisible();
  expect(screen.queryByRole("button", { name: "阅读附件正文" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "下载原始附件" })).toBeVisible();
  const content = confirmedContents({ ...result, attachments: [toolAttachment] }, run)[0];
  expect(readableContent(content)).toBe(false);
  expect(() => projectedArtifactText(stored, ref.mediaType, content.presentation)).toThrow(/暂时无法展开/);
});
it("keeps unmatched selectors incomplete instead of exporting the raw response", () => {
  const presentation = artifactPresentation(fixture(), attachment, ref.digest);
  expect(() => projectedArtifactText('{"other": "not the declared field"}', ref.mediaType, presentation)).toThrow(/部分内容尚未展开/);
});
