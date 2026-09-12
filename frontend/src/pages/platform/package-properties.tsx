import { Field, FieldGroup, TextField, ChoiceField } from "@/components/shared/form-field";
import { JsonSchemaEditor } from "@/components/platform-authoring/schema-composer/json-schema-editor";
import { Button } from "@/components/ui/button";
import type { NodeDefinition, PackageDefinition, WorkflowDefinition } from "@/lib/types/workflow-platform";
import { agentLabel, stepLabels, workflowSources } from "@/lib/platform-authoring/package-authoring";
import { MappingEditor, ConditionEditor } from "./package-mapping";
import { PresentationEditor } from "./package-presentation";
import { MultipleChoice, NumberProperty, SavedChoice, type AuthoringCatalog, type PropertyEdit } from "./package-controls";

type Context = { edit: PropertyEdit; definition: PackageDefinition; workflowKey: string; catalog: AuthoringCatalog };

export function WorkflowProperties({ workflow, edit, definition, workflowKey, catalog }: Context & { workflow: WorkflowDefinition }) {
  const sources = workflowSources(definition, workflowKey);
  const tools = catalog.tools.map((tool) => ({ ...tool, sourceValues: Object.entries(workflow.nodes).filter(([, node]) => (definition.agents[node.uses]?.tools ?? []).includes(tool.value)).map(([key]) => `nodes.${key}.output`) }));
  return <FieldGroup>
    <TextField label="任务流程名称" value={workflow.name ?? ""} onChange={(v) => edit(["name"], v)} />
    <TextField label="任务用途" value={workflow.description ?? ""} onChange={(v) => edit(["description"], v || undefined)} />
    <JsonSchemaEditor label="开始任务时填写的信息" schema={workflow.inputSchema} onChange={(v) => edit(["inputSchema"], v)} />
    <MappingEditor label="最终结果" value={workflow.outputMapping} sources={sources} targetSchema={workflow.outputSchema} onChange={(v) => edit(["outputMapping"], v)} />
    <JsonSchemaEditor label="最终结果的内容规则" schema={workflow.outputSchema} onChange={(v) => edit(["outputSchema"], v)} />
    <PresentationEditor value={workflow.presentation} onChange={(v) => edit(["presentation"], v)} inputSources={sources.slice(0, 1)} outputSources={[{ value: "workflow.output", label: "最终结果", schema: workflow.outputSchema }, ...sources.slice(1)]} tools={tools} />
    <Field label="执行与恢复">
      <ChoiceField label="某一步失败时" value={workflow.failurePolicy ?? "continue_independent"} onChange={(v) => edit(["failurePolicy"], v)} options={[{ value: "continue_independent", label: "继续完成不受影响的步骤" }, { value: "fail_fast", label: "停止启动其他步骤" }]} />
      <NumberProperty label="同时进行的步骤" value={workflow.maxParallelNodes} max={128} onChange={(v) => edit(["maxParallelNodes"], v)} />
      <NumberProperty label="整个任务最长等待（秒）" value={workflow.deadlineSeconds} max={604800} onChange={(v) => edit(["deadlineSeconds"], v)} />
    </Field>
  </FieldGroup>;
}

const states = [
  { value: "succeeded", label: "已完成" }, { value: "failed", label: "失败" }, { value: "skipped", label: "因条件不满足而跳过" },
  { value: "blocked", label: "因前置步骤未完成而停止" }, { value: "cancelled", label: "已取消" }, { value: "timed_out", label: "等待超时" },
];

export function NodeProperties({ node, edit, definition, workflowKey, nodeKey }: Context & { node: NodeDefinition; nodeKey: string }) {
  const labels = stepLabels(definition, workflowKey);
  return <FieldGroup>
    <h2 className="font-semibold">{labels[nodeKey]}</h2>
    <SavedChoice label="由谁完成" value={node.uses ?? ""} options={Object.keys(definition.agents).map((key) => ({ value: key, label: agentLabel(definition, key) }))} onChange={(v) => edit(["uses"], v)} missing="原助手已不可用，请重新选择" />
    <MappingEditor label="交给助手的信息" value={node.inputMapping} sources={workflowSources(definition, workflowKey, nodeKey)} targetSchema={definition.agents[node.uses]?.inputSchema} onChange={(v) => edit(["inputMapping"], v)} />
    <Field label="执行顺序" description="使用其他步骤的结果时，会自动等它完成。这里可以另外指定需要先完成的步骤。">
      <MultipleChoice label="还需要先完成" value={node.dependsOn} options={Object.entries(labels).filter(([key]) => key !== nodeKey).map(([value, label]) => ({ value, label }))} onChange={(v) => edit(["dependsOn"], v)} emptyText="当前没有其他步骤。" />
    </Field>
    {node.condition ? <><ConditionEditor label="执行条件" value={node.condition} sources={workflowSources(definition, workflowKey, nodeKey)} onChange={(v) => edit(["condition"], v)} /><Button variant="outline" onClick={() => edit(["condition"], undefined)}>移除执行条件</Button></> : <Button variant="outline" onClick={() => edit(["condition"], { op: "exists", args: [{ ref: "workflow.input" }] })}>设置执行条件</Button>}
    <Field label="遇到问题时" description="允许前置步骤失败后继续时，请为可能缺失的信息设置替代内容。">
      <MultipleChoice label="前置步骤出现哪些情况时仍可继续" value={node.acceptUpstreamStates ?? ["succeeded"]} options={states} onChange={(v) => edit(["acceptUpstreamStates"], v)} />
      {node.acceptUpstreamStates?.length === 0 && <p role="alert" className="text-sm text-destructive">请至少选择一种可以继续的情况。</p>}
      <NumberProperty label="最多尝试次数（含首次）" value={node.maxAttempts} max={10} onChange={(v) => edit(["maxAttempts"], v)} />
    </Field>
  </FieldGroup>;
}
