import type { AgentDefinition, Diagnostic, Json, JsonObject, PackageDefinition, WorkflowDefinition } from "@/lib/types/workflow-platform";
import { initialPackageSource, updateSource } from "./package-source";

export function freshKey(prefix: string) {
  return `${prefix}-${crypto.randomUUID().replaceAll("-", "").slice(0, 16)}`;
}

export function newAgent(index: number, modelRef = ""): AgentDefinition {
  return {
    name: `助手 ${index}`,
    inputSchema: { type: "object", properties: { request: { type: "string", title: "任务说明", minLength: 1 } }, required: ["request"] },
    outputSchema: { type: "string", title: "回答" },
    strategy: { kind: "model", modelRef, prompt: "根据用户填写的任务说明完成任务。清楚说明结论和仍然不确定的事项。" },
    tools: [], resources: [],
  };
}

export function newWorkflow(index: number, agentKey: string, agent: AgentDefinition): WorkflowDefinition {
  return {
    name: `任务流程 ${index}`, inputSchema: structuredClone(agent.inputSchema),
    outputSchema: structuredClone(agent.outputSchema),
    nodes: { first: { uses: agentKey, inputMapping: { ref: "workflow.input" } } },
    outputMapping: { ref: "nodes.first.output" },
  };
}

export function newPackageSource() {
  const agent = newAgent(1);
  let source = updateSource(initialPackageSource, ["metadata"], { key: freshKey("workflow"), name: "我的工作流", description: "" });
  source = updateSource(source, ["agents"], { assistant: agent });
  return updateSource(source, ["workflows"], { main: newWorkflow(1, "assistant", agent) });
}

export function agentLabel(definition: PackageDefinition, key: string) {
  const index = Object.keys(definition.agents).indexOf(key);
  return definition.agents[key]?.name || (index >= 0 ? `助手 ${index + 1}` : "待选择助手");
}

export function workflowLabel(definition: PackageDefinition, key: string) {
  return definition.workflows[key]?.name || `任务流程 ${Object.keys(definition.workflows).indexOf(key) + 1}`;
}

export function stepLabels(definition: PackageDefinition, workflowKey: string) {
  return Object.fromEntries(Object.entries(definition.workflows[workflowKey]?.nodes ?? {}).map(([key, node], index) => [key, `步骤 ${index + 1} · ${agentLabel(definition, node.uses)}`]));
}

export function workflowSources(definition: PackageDefinition, workflowKey: string, excludeStep?: string) {
  const workflow = definition.workflows[workflowKey];
  const labels = stepLabels(definition, workflowKey);
  return [
    { value: "workflow.input", label: "用户填写的信息", schema: workflow.inputSchema },
    ...Object.entries(workflow.nodes).filter(([key]) => key !== excludeStep).map(([key, node]) => ({
      value: `nodes.${key}.output`, label: `${labels[key]}的结果`, schema: definition.agents[node.uses]?.outputSchema,
    })),
  ];
}

export function hasStepReference(value: unknown, stepKey: string): boolean {
  if (!value || typeof value !== "object") return false;
  if (Array.isArray(value)) return value.some((item) => hasStepReference(item, stepKey));
  const object = value as Record<string, unknown>;
  if (typeof object.ref === "string" && (object.ref === `nodes.${stepKey}.output` || object.ref.startsWith(`nodes.${stepKey}.output.`))) return true;
  if (Object.hasOwn(object, "value")) return false;
  if (object.object && typeof object.object === "object" && !Array.isArray(object.object)) {
    return Object.values(object.object).some((item) => hasStepReference(item, stepKey));
  }
  return Object.values(object).some((item) => hasStepReference(item, stepKey));
}

export function stepRemovalBlockers(workflow: WorkflowDefinition, stepKey: string, labels: Record<string, string>) {
  const blockers = Object.entries(workflow.nodes).filter(([key, node]) => key !== stepKey && ((node.dependsOn ?? []).includes(stepKey) || hasStepReference(node, stepKey))).map(([key]) => labels[key]);
  if (hasStepReference(workflow.outputMapping, stepKey)) blockers.push("最终结果");
  if (hasStepReference(workflow.presentation, stepKey)) blockers.push("结果页面");
  return blockers;
}

export function objectValue(value: Json | undefined): JsonObject | undefined {
  return value && typeof value === "object" && !Array.isArray(value) ? value : undefined;
}

const diagnosticMessages: Record<string, string> = {
  dependency_cycle: "这些步骤互相等待。请调整执行顺序、输入来源或执行条件，确保能够从第一个步骤开始。",
  unknown_agent: "请为此步骤选择一个可用助手。",
  unknown_node: "前置步骤已不存在。请选择其他步骤或移除等待要求。",
  unknown_reference: "所选信息已不存在。请重新选择输入或结果来源。",
  invalid_reference: "请重新选择信息来源。",
  invalid_reference_scope: "该信息在此处不可用。请从可选来源中重新选择。",
  mapping_type: "来源内容与接收字段的类型不一致。请调整字段规则或为每个字段分别选择来源。",
  mapping_constraint: "来源内容不能保证满足接收字段的限制。请调整取值范围或选择其他来源。",
  missing_mapping: "仍有必填内容没有来源，或来源可能缺失。请补齐字段，并为可能缺失的信息设置替代内容。",
  invalid_mapping: "请补全这组信息来源。",
  invalid_condition: "请补全执行条件的判断内容。",
  presentation_type: "所选内容不适合这种展示方式。请更换来源或展示方式。",
  duplicate_hint: "同一个填写项只能设置一次填写提示。",
  invalid_schema: "字段规则有冲突或未填完整。请检查类型、必填项、默认内容和取值范围。",
  unsupported_schema: "导入文件包含尚不支持的字段规则。请使用字段编辑器调整，或导入其他文件。",
  invalid_value: "填写内容不符合字段规则。请检查内容类型和取值范围。",
  invalid_definition: "这项设置未填完整或超出允许范围。请检查后重试。",
  invalid_yaml: "无法读取导入文件。请重新选择有效的工作流文件。",
  unsafe_yaml: "无法使用此导入文件。请重新导出工作流后导入。",
  source_limit: "工作流文件太大。请减少文件内容后重试。",
};

export function authoringDiagnostic(diagnostic: Diagnostic, definition?: PackageDefinition) {
  const parts = diagnostic.path.replace(/^\$\.?/, "").split(".");
  let selection: string[] = [];
  let label = "工作流设置";
  if (definition && parts[0] === "agents" && definition.agents[parts[1]]) {
    selection = parts.slice(0, 2); label = agentLabel(definition, parts[1]);
  } else if (definition && parts[0] === "workflows" && definition.workflows[parts[1]]) {
    selection = parts.slice(0, 2); label = workflowLabel(definition, parts[1]);
    if (parts[2] === "nodes" && definition.workflows[parts[1]].nodes[parts[3]]) {
      selection = parts.slice(0, 4); label += ` · ${stepLabels(definition, parts[1])[parts[3]]}`;
    }
  }
  const fields: Record<string, string> = { modelRef: "AI 服务", toolId: "服务操作", prompt: "助手任务说明", inputSchema: "填写项", outputSchema: "结果字段", inputMapping: "输入来源", outputMapping: "最终结果", condition: "执行条件", dependsOn: "执行顺序", strategy: "完成方式", tools: "服务操作", resources: "可用连接", budget: "用量与等待限制", presentation: "结果页面", maxAttempts: "重试次数", name: "名称" };
  const field = [...parts].reverse().find((part) => fields[part]);
  if (field) label += ` · ${fields[field]}`;
  const requiredChoice: Record<string, string> = { modelRef: "请选择这位助手使用的 AI 服务。尚未添加时，可前往连接设置，添加后返回继续。", toolId: "请选择要执行的服务操作。", prompt: "请填写助手要完成的任务和回答要求。" };
  return { label, selection, message: (diagnostic.code === "invalid_definition" && field ? requiredChoice[field] : undefined) ?? diagnosticMessages[diagnostic.code] ?? "这项设置需要调整。请检查相关内容后再次检查工作流。" };
}
