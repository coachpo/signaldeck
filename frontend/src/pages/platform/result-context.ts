import type { ExecutionEvidence, Json, JsonObject, RunDetail } from "@/lib/types/workflow-platform";
import type { ResultSection } from "@/lib/types/result";
import { asObject, type MappingSource } from "@/lib/platform-authoring/mapping-sources";

export function objectValue(value: Json | undefined): JsonObject | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value : undefined;
}

export function runWorkflow(run: RunDetail) {
  return run.spec.definition.workflows[run.workflowKey];
}

export function stepName(run: RunDetail, nodeId: string) {
  const workflow = runWorkflow(run);
  const node = workflow?.nodes[nodeId];
  const index = run.spec.plan.nodeOrder.indexOf(nodeId);
  return (node && run.spec.definition.agents[node.uses]?.name) || (index >= 0 ? `步骤 ${index + 1}` : "其他步骤");
}

export function runSources(run: RunDetail, excludeStep?: string): MappingSource[] {
  const workflow = runWorkflow(run);
  return [
    { value: "workflow.input", label: "用户填写的信息", schema: workflow?.inputSchema },
    ...run.spec.plan.nodeOrder.filter((id) => id !== excludeStep).map((id) => {
      const node = workflow?.nodes[id];
      return { value: `nodes.${id}.output`, label: `${stepName(run, id)}的结果`, schema: node ? run.spec.definition.agents[node.uses]?.outputSchema : undefined };
    }),
  ];
}

export function mappingReferences(value: JsonObject): string[] {
  if (Object.hasOwn(value, "value")) return [];
  if (typeof value.ref === "string") return [value.ref, ...mappingReferences(asObject(value.onMissing))];
  if (value.object) return Object.values(asObject(value.object)).flatMap((child) => mappingReferences(asObject(child)));
  if (Array.isArray(value.array)) return value.array.flatMap((child) => mappingReferences(asObject(child)));
  return [];
}

export function frozenTool(run: RunDetail, toolId?: string | null) {
  if (!toolId) return undefined;
  return run.spec.pluginReleases.flatMap((release) => Array.isArray(release.tools) ? release.tools : [])
    .map(objectValue).find((tool) => tool?.toolId === toolId);
}

export function toolName(run: RunDetail | undefined, toolId?: string | null, ordinal = 1) {
  const tool = run && frozenTool(run, toolId);
  const title = objectValue(tool?.inputSchema)?.title;
  if (typeof title === "string" && title.trim()) return title;
  return `${tool?.effect === "read" ? "读取资料" : tool?.effect === "write" ? "保存或更新资料" : "服务操作"} ${ordinal}`;
}

export function evidenceName(item: ExecutionEvidence, run?: RunDetail) {
  if (item.kind === "node") return run ? stepName(run, item.nodeId) : "任务步骤";
  if (item.kind === "agent") return "处理任务";
  if (item.kind === "model") return "生成内容";
  if (item.kind === "attempt") return "联系服务";
  const ordinal = run ? Math.max(1, run.evidence.filter((entry) => entry.kind === "tool").findIndex((entry) => entry.id === item.id) + 1) : 1;
  return toolName(run, item.toolId, ordinal);
}

export function sectionSchema(run: RunDetail | undefined, section: ResultSection) {
  if (!run) return undefined;
  const workflow = runWorkflow(run);
  if (!workflow?.presentation) {
    const item = run.evidence.find((evidence) => evidence.id === section.evidenceId);
    if (!item) return workflow?.outputSchema;
    if (item.kind === "tool") return objectValue(frozenTool(run, item.toolId)?.outputSchema);
    const node = workflow.nodes[item.nodeId];
    return node ? run.spec.definition.agents[node.uses]?.outputSchema : undefined;
  }
  const candidates = workflow?.presentation?.sections?.filter((item) => item.label === section.label && item.kind === section.kind && (!section.nodeId || item.ref.startsWith(`nodes.${section.nodeId}.`))) ?? [];
  const declaration = candidates.length === 1 ? candidates[0] : undefined;
  if (!declaration) return undefined;
  const parts = declaration.ref.split(".");
  const node = workflow.nodes[parts[1]];
  let schema: JsonObject | undefined = parts[0] === "workflow" ? workflow.outputSchema : node && run.spec.definition.agents[node.uses]?.outputSchema;
  for (const part of parts.slice(parts[0] === "workflow" ? 2 : 3)) {
    schema = schema?.type === "array" ? objectValue(schema.items) : objectValue(objectValue(schema?.properties)?.[part]);
  }
  return schema;
}

export function recordedTime(value?: string | null) {
  return value ? new Date(value).toLocaleString() : "未记录";
}
