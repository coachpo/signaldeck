import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import type { RunResult, ResultSection } from "@/lib/types/result";
import { runFixture } from "./fixtures";
import { groupResultSections } from "./result-section-groups";
import { DeclaredResultSections } from "./result-sections";
import { confirmedContents, exportMarkdown } from "./result-delivery";
import { ResultExport } from "./result-export";

const body = "访谈记录原文\nUser code: schema = 42;";
const sections: ResultSection[] = [
  { kind: "value", label: "任务结果", value: body },
  { kind: "value", label: "资料整理 · 步骤结果", value: body, nodeId: "answer", evidenceId: "node-a" },
  { kind: "value", label: "资料保存 · 服务结果", value: body, nodeId: "answer", evidenceId: "tool-a" },
];
function genericRun() {
  const run = structuredClone(runFixture);
  delete run.spec.definition.workflows.main.presentation;
  return run;
}
const result: RunResult = { runId: "run-1", title: "访谈记录", status: "succeeded", contentStatus: "available", body: null, receipt: null, dataTime: null, createdAt: "2026-09-12T00:00:00Z", finishedAt: null, cancelRequestedAt: null, origin: { kind: "manual" }, sections, sources: [], missing: [], attachments: [], unknownEvidenceIds: [], freshness: [], errorCode: null };
afterEach(() => vi.restoreAllMocks());
it("reads equal generic content once while retaining every source link and the original values", () => {
  const before = JSON.stringify(sections);
  const search = new URLSearchParams({ history: "q=访谈&offset=25" });
  render(<MemoryRouter><DeclaredResultSections sections={sections} run={genericRun()} search={search} /></MemoryRouter>);
  expect(screen.getAllByText(body, { normalizer: (value) => value })).toHaveLength(1);
  expect(screen.getByRole("link", { name: "查看资料整理 · 步骤结果" })).toHaveAttribute("href", "/runs/run-1?tab=evidence&target=node-a&history=q%3D%E8%AE%BF%E8%B0%88%26offset%3D25");
  expect(screen.getByRole("link", { name: "查看资料保存 · 服务结果" })).toHaveAttribute("href", "/runs/run-1?tab=evidence&target=tool-a&history=q%3D%E8%AE%BF%E8%B0%88%26offset%3D25");
  expect(JSON.stringify(sections)).toBe(before);
});
it("preserves separately authored sections even when their confirmed text is identical", () => {
  const run = genericRun();
  run.spec.definition.workflows.main.presentation = { version: "signaldeck.presentation/1", sections: [
    { kind: "value", label: "任务结果", ref: "workflow.output" },
    { kind: "value", label: "资料整理 · 步骤结果", ref: "nodes.answer.output" },
  ] };
  const declared = sections.slice(0, 2);
  render(<MemoryRouter><DeclaredResultSections sections={declared} run={run} search={new URLSearchParams()} /></MemoryRouter>);
  expect(screen.getAllByText(body, { normalizer: (value) => value })).toHaveLength(2);
  const selected = confirmedContents({ ...result, sections: declared }, run);
  expect(selected).toHaveLength(2);
  expect(exportMarkdown({ ...result, sections: declared }, selected, {}).split(body)).toHaveLength(3);
});
it("uses exact typed equality without trimming strings or merging distinct list contents", () => {
  const values = ["text", "text ", false, "false", 0, null, ["a", "b"], ["b", "a"]];
  const original = values.map((value, index): ResultSection => ({ kind: "value", label: `结果 ${index + 1}`, value }));
  expect(groupResultSections([...original, { ...original[0], label: "同一正文" }], genericRun())).toHaveLength(values.length);
  expect(groupResultSections(sections)).toHaveLength(3);
});
it("copies and downloads the readable string once by default without quoting or fencing its text", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  const create = vi.fn().mockReturnValue("blob:result");
  Object.defineProperty(URL, "createObjectURL", { configurable: true, value: create });
  Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  render(<QueryClientProvider client={new QueryClient()}><ResultExport result={result} run={genericRun()} /></QueryClientProvider>);
  expect(screen.getByText("选择复制与导出的内容（已选 1 / 1 项）")).toBeVisible();
  expect(screen.queryByText(/本次没有单独的文字正文/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "复制所选正文" }));
  await screen.findByText("所选确认内容已复制。");
  const copied = writeText.mock.calls[0][0] as string;
  expect(copied.split(body)).toHaveLength(2);
  expect(copied).not.toContain(JSON.stringify(body));
  expect(copied).not.toContain("```");
  expect(copied).not.toContain("未纳入本文件的内容");
  fireEvent.click(screen.getByRole("button", { name: "导出 Markdown" }));
  await screen.findByText("已请求下载所选确认内容。");
  const downloaded = await new Promise<string>((resolve) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.readAsText(create.mock.calls[0][0]);
  });
  expect(downloaded).toBe(copied);
});

it("retains deselected content while frozen display information finishes loading", () => {
  const client = new QueryClient();
  const { rerender } = render(<QueryClientProvider client={client}><ResultExport result={result} /></QueryClientProvider>);
  fireEvent.click(screen.getByText(/选择复制与导出的内容/));
  for (const checkbox of screen.getAllByRole("checkbox")) fireEvent.click(checkbox);
  rerender(<QueryClientProvider client={client}><ResultExport result={result} run={genericRun()} /></QueryClientProvider>);
  expect(screen.getByText("选择复制与导出的内容（已选 0 / 1 项）")).toBeVisible();
  expect(screen.getByRole("button", { name: "复制所选正文" })).toBeDisabled();
  fireEvent.click(screen.getByRole("checkbox"));
  expect(screen.getByRole("button", { name: "复制所选正文" })).toBeEnabled();
});

it("waits for frozen display information before default delivery can include duplicates", () => {
  const client = new QueryClient();
  const { rerender } = render(<QueryClientProvider client={client}><ResultExport result={result} pendingRun /></QueryClientProvider>);
  expect(screen.getByRole("button", { name: "复制所选正文" })).toBeDisabled();
  expect(screen.getByText("正在准备正文与来源，完成后即可复制或导出。")).toBeVisible();
  rerender(<QueryClientProvider client={client}><ResultExport result={result} run={genericRun()} /></QueryClientProvider>);
  expect(screen.getByRole("button", { name: "复制所选正文" })).toBeEnabled();
  expect(screen.getByText("选择复制与导出的内容（已选 1 / 1 项）")).toBeVisible();
});
