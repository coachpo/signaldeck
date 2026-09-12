import type { ResultSection } from "@/lib/types/result";
import type { Json, RunDetail } from "@/lib/types/workflow-platform";
import { runWorkflow } from "./result-context";

export type SectionSource = Pick<ResultSection, "label" | "evidenceId" | "nodeId"> & { index: number };
type SectionGroup = { section: ResultSection; index: number; sources: SectionSource[] };

function sameValue(left: Json, right: Json): boolean {
  if (left === right) return true;
  if (left === null || right === null || typeof left !== "object" || typeof right !== "object") return false;
  if (Array.isArray(left) || Array.isArray(right)) return Array.isArray(left) && Array.isArray(right) && left.length === right.length && left.every((value, index) => sameValue(value, right[index]));
  const keys = Object.keys(left);
  return keys.length === Object.keys(right).length && keys.every((key) => Object.hasOwn(right, key) && sameValue(left[key], right[key]));
}

/** Unnamed presentation uses content identity; authored sections retain their boundaries. */
export function groupResultSections(sections: ResultSection[], run?: RunDetail): SectionGroup[] {
  const workflow = run && runWorkflow(run);
  const generic = !!workflow && !workflow.presentation;
  const groups: SectionGroup[] = [];
  sections.forEach((section, index) => {
    const source = { index, label: section.label, evidenceId: section.evidenceId, nodeId: section.nodeId };
    const existing = generic && section.kind === "value" ? groups.find((group) => group.section.kind === "value" && sameValue(group.section.value, section.value)) : undefined;
    if (existing) existing.sources.push(source);
    else groups.push({ section, index, sources: [source] });
  });
  return groups;
}
