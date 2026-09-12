import type { ResultAttachment } from "@/lib/types/result";
import type { Json, PresentationSection, RunDetail } from "@/lib/types/workflow-platform";
import { findArtifacts } from "./artifact-references";
import { runWorkflow } from "./result-context";
import { fenced } from "./result-text";

type SelectedSection = { kind: Exclude<PresentationSection["kind"], "link">; label: string; path: string[] };
export type ArtifactPresentation = { sections: SelectedSection[]; unavailable?: boolean };

/** Resolve only selectors owned by this artifact's frozen workflow or node output. */
export function artifactPresentation(run: RunDetail | undefined, attachment: ResultAttachment, digest: string): ArtifactPresentation | undefined {
  if (!run) return attachment.evidenceId ? { sections: [], unavailable: true } : undefined;
  const workflow = runWorkflow(run);
  const item = attachment.evidenceId ? run.evidence.find((evidence) => evidence.id === attachment.evidenceId) : undefined;
  // Tool outputs may differ from their node's mapped output. A node selector is
  // not evidence that its tool envelope has the same shape or business meaning.
  if (attachment.evidenceId && (!item || item.kind !== "node")) return { sections: [], unavailable: true };
  if (!workflow?.presentation) return undefined;
  const source = item ? item.output : run.output;
  const location = findArtifacts(source).find(({ ref }) => ref.digest === digest);
  if (!location) return { sections: [], unavailable: true };
  const storedPath = location.path.split(".").slice(1);
  if (storedPath.at(-1) === "$artifact") storedPath.pop();
  const prefix = item ? `nodes.${item.nodeId}.output` : "workflow.output";
  const sections = (workflow.presentation.sections ?? []).flatMap((declaration): SelectedSection[] => {
    if (declaration.kind === "link" || (declaration.ref !== prefix && !declaration.ref.startsWith(`${prefix}.`))) return [];
    const selectedPath = declaration.ref.slice(prefix.length).split(".").filter(Boolean);
    const common = Math.min(storedPath.length, selectedPath.length);
    if (!storedPath.slice(0, common).every((part, index) => part === selectedPath[index])) return [];
    return [{ kind: declaration.kind, label: declaration.label, path: selectedPath.slice(storedPath.length) }];
  });
  return { sections, unavailable: !sections.length };
}

export function projectedArtifactValues(text: string, mediaType: string, presentation: ArtifactPresentation) {
  if (presentation.unavailable) return [];
  let root: Json = text;
  if (mediaType.includes("json")) {
    try { root = JSON.parse(text) as Json; } catch { return []; }
  }
  return presentation.sections.flatMap((section) => {
    let value: Json | undefined = root;
    for (const part of section.path) {
      if (!value || typeof value !== "object") { value = undefined; break; }
      value = Array.isArray(value) ? value[Number(part)] : value[part];
    }
    return value === undefined ? [] : [{ kind: section.kind, label: section.label, value }];
  });
}

export function projectedArtifactText(text: string, mediaType: string, presentation?: ArtifactPresentation) {
  if (!presentation) return text;
  const values = projectedArtifactValues(text, mediaType, presentation);
  if (!values.length) throw new Error("附件正文暂时无法展开。可从结果页下载原始附件核对。");
  if (values.length < presentation.sections.length) throw new Error("附件中部分内容尚未展开。请在结果页核对后再导出。");
  return values.map((section) => {
    const title = section.label.replace(/[\r\n]/g, " ");
    const body = section.kind === "receipt" ? "此项保存已确认。" : section.kind === "markdown" && typeof section.value === "string" ? section.value : fenced(JSON.stringify(section.value, null, 2), "json");
    return `## ${title}\n\n${body}`;
  }).join("\n\n");
}
