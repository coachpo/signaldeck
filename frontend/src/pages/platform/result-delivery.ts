import type { RunResult } from "@/lib/types/result";
import type { ArtifactRef, Json, RunDetail } from "@/lib/types/workflow-platform";
import { findArtifacts } from "./artifact-references";
import { safePluginPageUrl } from "./plugin-links";
import { originLabels, resultStatusLabels, contentStatusLabels } from "./result-labels";
import { artifactPresentation, type ArtifactPresentation } from "./result-artifact-presentation";
import { fenced } from "./result-text";
import { groupResultSections, type SectionSource } from "./result-section-groups";
export { fenced } from "./result-text";

export type ConfirmedContent = {
  id: string;
  label: string;
  text?: string;
  format: "markdown" | "json" | "text";
  artifact?: ArtifactRef;
  evidenceId?: string | null;
  presentation?: ArtifactPresentation;
  aliases?: string[];
  sources?: SectionSource[];
};

/** Consume only the server's frozen, confirmed projection; never inspect model attempts. */
export function confirmedContents(result: RunResult, run?: RunDetail): ConfirmedContent[] {
  const sections = result.sections ?? [];
  const content: ConfirmedContent[] = groupResultSections(sections, run).map(({ section, index, sources }) => ({
    id: `section:${index}`, label: section.label, evidenceId: section.evidenceId,
    aliases: sources.map((source) => `section:${source.index}`), sources,
    format: section.kind === "receipt" ? "text" : section.kind === "link" || (section.kind === "markdown" && typeof section.value === "string") ? "markdown" : typeof section.value === "string" ? "text" : "json",
    text: section.kind === "receipt" ? "此项保存已确认。" : typeof section.value === "string" && section.kind !== "link"
      ? section.value
      : section.kind === "link" && safePluginPageUrl(section.href)
        ? `[${section.label}](${section.href})`
        : JSON.stringify(section.value, null, 2),
  }));
  if (!sections.length) {
    if (result.body !== null) content.push({ id: "body", label: "结果正文", format: "markdown", text: result.body });
    if (result.receipt !== null) content.push({ id: "receipt", label: "保存回执", format: "text", text: "此项保存已确认。" });
  }
  result.attachments.forEach((attachment, i) => {
    findArtifacts(attachment.reference).forEach(({ ref }, j) => {
      const presentation = artifactPresentation(run, attachment, ref.digest);
      content.push({ id: `artifact:${i}:${j}`, label: attachment.label, artifact: ref,
        presentation,
        evidenceId: attachment.evidenceId,
        format: presentation ? "markdown" : ref.mediaType.includes("json") ? "json" : ref.mediaType.startsWith("text/") ? "markdown" : "text" });
    });
  });
  return content;
}
export function readableContent(item: ConfirmedContent) {
  return !item.presentation?.unavailable && (!item.artifact || item.artifact.mediaType.startsWith("text/") || item.artifact.mediaType.includes("json"));
}
function literal(value: Json) { return fenced(JSON.stringify(value, null, 2), "json"); }
export function contentMarkdown(item: ConfirmedContent, text: string) {
  return item.format === "json" ? fenced(text, "json") : text;
}
export function exportMarkdown(result: RunResult, selected: ConfirmedContent[], loaded: Record<string, string>, resultUrl?: string): string {
  if (!selected.length) throw new Error("请先选择可复制或导出的确认内容。");
  const all = confirmedContents(result);
  const lines = [
    `# ${result.title.replace(/[\r\n]/g, " ")}`,
    `状态：${resultStatusLabels[result.status] ?? result.status}；内容：${contentStatusLabels[result.contentStatus]}`,
    `来源：${originLabels[result.origin.kind] ?? result.origin.kind}`,
    `创建时间：${result.createdAt}；完成时间：${result.finishedAt ?? "尚未结束"}`,
    `数据时间：${result.dataTime ?? "未提供"}`,
  ];
  if (result.errorCode && result.status !== "cancelled") lines.push("本次任务未能全部完成，请打开结果查看处理方式。");
  if (result.cancelRequestedAt) lines.push(`取消请求时间：${result.cancelRequestedAt}。已经确认的外部操作仍会保留。`);
  if (result.readUnknownEvidenceIds?.length) lines.push(`读取结果未确认；该读取不涉及保存。请打开执行过程核对`);
  if (result.contentStatus === "unknown") lines.push("保存状态待核实；以下仅为已确认内容，不代表所有操作成功。");
  if (result.contentStatus === "partial") lines.push("本次仅有部分确认内容。");
  if (result.missing.length) lines.push(`缺失资料：\n${literal(result.missing)}`);
  if (result.executionIssues?.length) lines.push(`未完成执行：\n${literal(result.executionIssues)}`);
  if (result.skipped?.length) lines.push(`跳过分支：\n${literal(result.skipped)}`);
  if (result.sources.length) lines.push(`资料来源：\n${literal(result.sources)}`);
  for (const value of result.freshness) {
    if (!value || typeof value !== "object" || Array.isArray(value) || typeof value.hit !== "boolean") continue;
    lines.push(`${value.hit ? "沿用此前取得的资料" : "本次重新取得资料"}；取得时间：${typeof value.fetchedAt === "string" ? value.fetchedAt : "未记录"}；可复用至：${typeof value.expiresAt === "string" ? value.expiresAt : "未记录"}`);
  }
  for (const item of selected) {
    const text = item.artifact ? loaded[item.id] : item.text;
    if (text === undefined) throw new Error("所选附件尚未读取完成，请重试读取或取消选择。");
    lines.push(`## ${item.label.replace(/[\r\n]/g, " ")}`, contentMarkdown(item, text));
    if (item.artifact) lines.push("以上附件内容按原文保留。");
  }
  const includedIds = new Set(selected.flatMap((item) => item.aliases ?? [item.id]));
  const excluded = all.filter((item) => !includedIds.has(item.id));
  if (excluded.length) lines.push("## 未纳入本文件的内容", ...excluded.map((item) => `- ${item.label.replace(/[\r\n]/g, " ")}${item.artifact ? " · 附件" : ""}`));
  if (result.deferredSections?.length) lines.push("## 保存在附件中的内容", literal(result.deferredSections), "这些内容保存在附件中；所选附件按原文包含。");
  if (safePluginPageUrl(resultUrl)) lines.push(`[查看完整结果和全部来源](${resultUrl})`);
  return lines.join("\n\n") + "\n";
}

export function downloadMarkdown(title: string, content: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  try {
    link.href = url;
    link.download = `${title.replace(/[\\/:*?"<>|\r\n]/g, "_").slice(0, 120) || "任务结果"}.md`;
    document.body.append(link);
    link.click();
  } finally {
    link.remove();
    URL.revokeObjectURL(url);
  }
}
