import type { RunResult } from "@/lib/types/result";
import type { ArtifactRef, Json } from "@/lib/types/workflow-platform";
import { findArtifacts } from "./artifact-references";
import { safePluginPageUrl } from "./plugin-links";
import { originLabels, resultStatusLabels } from "./result-labels";

export type ConfirmedContent = {
  id: string;
  label: string;
  text?: string;
  format: "markdown" | "json" | "text";
  artifact?: ArtifactRef;
  evidenceId?: string | null;
};

/** Consume only the server's frozen, confirmed projection; never inspect model attempts. */
export function confirmedContents(result: RunResult): ConfirmedContent[] {
  const sections = result.sections ?? [];
  const content: ConfirmedContent[] = sections.map((section, i) => ({
    id: `section:${i}`, label: section.label, evidenceId: section.evidenceId,
    format: section.kind === "markdown" && typeof section.value === "string" ? "markdown" : "json",
    text: section.kind === "markdown" && typeof section.value === "string"
      ? section.value
      : section.kind === "link" && safePluginPageUrl(section.href)
        ? JSON.stringify({ value: section.value, href: section.href }, null, 2)
        : JSON.stringify(section.value, null, 2),
  }));
  if (!sections.length) {
    if (result.body !== null) content.push({ id: "body", label: "结果正文", format: "markdown", text: result.body });
    if (result.receipt !== null) content.push({ id: "receipt", label: "保存回执", format: "json", text: JSON.stringify(result.receipt, null, 2) });
  }
  result.attachments.forEach((attachment, i) => {
    findArtifacts(attachment.reference).forEach(({ ref }, j) => {
      content.push({ id: `artifact:${i}:${j}`, label: attachment.label, artifact: ref,
        evidenceId: attachment.evidenceId,
        format: ref.mediaType.includes("json") ? "json" : ref.mediaType.startsWith("text/") ? "markdown" : "text" });
    });
  });
  return content;
}
export function readableContent(item: ConfirmedContent) {
  return !item.artifact || item.artifact.mediaType.startsWith("text/") || item.artifact.mediaType.includes("json");
}
export function fenced(text: string, language = "") {
  let longest = 2;
  for (const match of text.matchAll(/`+/g)) longest = Math.max(longest, match[0].length);
  const fence = "`".repeat(longest + 1);
  return `${fence}${language}\n${text}\n${fence}`;
}
function literal(value: Json) { return fenced(JSON.stringify(value, null, 2), "json"); }
export function contentMarkdown(item: ConfirmedContent, text: string) {
  return item.format === "markdown" ? text : fenced(text, item.format === "json" ? "json" : "text");
}
export function exportMarkdown(result: RunResult, selected: ConfirmedContent[], loaded: Record<string, string>): string {
  if (!selected.length) throw new Error("请先选择可复制或导出的确认内容。");
  const all = confirmedContents(result);
  const lines = [
    `# ${result.title.replace(/[\r\n]/g, " ")}`,
    `运行：${result.runId}`,
    `状态：${resultStatusLabels[result.status] ?? result.status}；内容状态：${result.contentStatus}`,
    `来源：${originLabels[result.origin.kind] ?? result.origin.kind}`,
    `创建时间：${result.createdAt}；完成时间：${result.finishedAt ?? "尚未结束"}`,
    `数据时间：${result.dataTime ?? "未提供"}`,
    `运行来源记录：\n${literal(result.origin as unknown as Json)}`,
  ];
  if (result.errorCode) lines.push(`执行错误码：${result.errorCode}${result.errorCategory ? `；安全类别：${result.errorCategory}` : ""}`);
  if (result.cancelRequestedAt) lines.push(`取消请求时间：${result.cancelRequestedAt}。已经确认的外部操作仍会保留。`);
  if (result.readUnknownEvidenceIds?.length) lines.push(`读取结果未确认；该读取不涉及保存。执行证据：${result.readUnknownEvidenceIds.join("、")}`);
  if (result.contentStatus === "unknown") lines.push("保存状态待核实；以下仅为已确认内容，不代表所有操作成功。");
  if (result.contentStatus === "partial") lines.push("本次仅有部分确认内容。");
  if (result.missing.length) lines.push(`缺失资料：\n${literal(result.missing)}`);
  if (result.executionIssues?.length) lines.push(`未完成执行：\n${literal(result.executionIssues)}`);
  if (result.skipped?.length) lines.push(`跳过分支：\n${literal(result.skipped)}`);
  if (result.sources.length) lines.push(`资料来源：\n${literal(result.sources)}`);
  if (result.freshness.length) lines.push(`新鲜度记录：\n${literal(result.freshness)}`);
  for (const item of selected) {
    const text = item.artifact ? loaded[item.id] : item.text;
    if (text === undefined) throw new Error("所选附件尚未读取完成，请重试读取或取消选择。");
    lines.push(`## ${item.label.replace(/[\r\n]/g, " ")}`, contentMarkdown(item, text));
    if (item.evidenceId) lines.push(`确认来源：${item.evidenceId}`);
    if (item.artifact) lines.push(`产物：${item.artifact.digest}（${item.artifact.mediaType}）`);
  }
  const excluded = all.filter((item) => !selected.some((chosen) => chosen.id === item.id));
  if (excluded.length) lines.push("## 未纳入本文件的内容", ...excluded.map((item) => `- ${item.label.replace(/[\r\n]/g, " ")}${item.artifact ? ` · ${item.artifact.digest} · ${item.artifact.mediaType}` : ""}`));
  if (result.deferredSections?.length) lines.push("## 延后解析的声明", literal(result.deferredSections), "声明的具体字段仍保存在原始产物中；本文件不推测其映射，所选附件按原文包含。");
  return lines.join("\n\n") + "\n";
}

export function downloadMarkdown(runId: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  try {
    link.href = url;
    link.download = `result-${runId.replace(/[^a-zA-Z0-9_-]/g, "_")}.md`;
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    URL.revokeObjectURL(url);
  }
}
