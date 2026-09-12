import { useState } from "react";
import { Link } from "react-router";
import { Field, FieldGroup, TextField, ChoiceField } from "@/components/shared/form-field";
import { JsonSchemaEditor } from "@/components/platform-authoring/schema-composer/json-schema-editor";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { AgentDefinition } from "@/lib/types/workflow-platform";
import { MappingEditor } from "./package-mapping";
import { MultipleChoice, NumberProperty, SavedChoice, type AuthoringCatalog, type PropertyEdit } from "./package-controls";

const budgets = [
  ["maxModelRequests", "最多思考次数", 1000], ["maxToolCalls", "最多服务操作次数", 10000],
  ["maxTokens", "总模型用量上限（模型计量单位）", undefined], ["maxOutputTokens", "单次回答上限（模型计量单位）", undefined],
  ["deadlineSeconds", "最长等待（秒）", 86400], ["maxParallelTools", "同时进行的服务操作", 128],
] as const;

export function AgentProperties({ agent, edit, catalog }: { agent: AgentDefinition; edit: PropertyEdit; catalog: AuthoringCatalog }) {
  const strategy = agent.strategy;
  // Switching methods is explicit; the in-session alternative retains the user's original instructions.
  const [alternatives, setAlternatives] = useState<Partial<Record<AgentDefinition["strategy"]["kind"], AgentDefinition["strategy"]>>>({});
  const tool = strategy.kind === "deterministic" ? catalog.tools.find((item) => item.value === strategy.toolId) : undefined;
  const inputs = [{ value: "agent.input", label: "交给助手的信息", schema: agent.inputSchema }];
  return <FieldGroup>
    <TextField label="助手名称" value={agent.name ?? ""} onChange={(v) => edit(["name"], v)} />
    <ChoiceField label="完成方式" value={strategy.kind} options={[{ value: "model", label: "由 AI 阅读、思考并完成" }, { value: "deterministic", label: "直接执行服务操作" }]} onChange={(kind) => {
      setAlternatives((previous) => ({ ...previous, [strategy.kind]: strategy }));
      const saved = alternatives[kind as AgentDefinition["strategy"]["kind"]];
      const next = saved ?? (kind === "model" ? { kind: "model" as const, modelRef: catalog.models[0]?.value ?? "", prompt: "请根据收到的信息完成任务。" } : { kind: "deterministic" as const, toolId: "", inputMapping: { ref: "agent.input" }, outputMapping: { ref: "tool.output" } });
      edit([], next.kind === "deterministic" ? { ...agent, strategy: next, tools: Array.from(new Set([...(agent.tools ?? []), ...(next.toolId ? [next.toolId] : [])])) } : { ...agent, strategy: next });
    }} />
    {strategy.kind === "model" ? <>
      <SavedChoice label="使用的 AI 服务" value={strategy.modelRef} options={catalog.models} onChange={(v) => edit(["strategy", "modelRef"], v)} missing="已保存的 AI 服务（当前不可用）" />
      {!catalog.models.length && <p className="text-sm text-muted-foreground">请先到<Link className="underline" to="/resources">连接设置</Link>添加 AI 服务，回来后继续选择。</p>}
      <Field label="助手任务说明" description="写明要完成的目标、判断要求及期望的回答方式。"><Textarea aria-label="助手任务说明" value={strategy.prompt} onChange={(e) => edit(["strategy", "prompt"], e.target.value)} className="min-h-40" /></Field>
    </> : <>
      <SavedChoice label="执行的服务操作" value={strategy.toolId} options={catalog.tools} onChange={(v) => edit([], { ...agent, strategy: { ...strategy, toolId: v }, tools: Array.from(new Set([...(agent.tools ?? []), v])) })} missing="已保存的服务操作（当前不可用）" />
      {tool?.effect === "write" && <p className="text-sm text-muted-foreground">此操作会修改外部服务中的内容。运行前请确认输入和连接。</p>}
      <MappingEditor label="传给服务的信息" value={strategy.inputMapping ?? { ref: "agent.input" }} sources={inputs} targetSchema={tool?.inputSchema} onChange={(v) => edit(["strategy", "inputMapping"], v)} />
      <MappingEditor label="助手返回的结果" value={strategy.outputMapping ?? { ref: "tool.output" }} sources={[...inputs, { value: "tool.output", label: "服务返回的结果", schema: tool?.outputSchema }]} targetSchema={agent.outputSchema} onChange={(v) => edit(["strategy", "outputMapping"], v)} />
    </>}
    <MultipleChoice label="允许使用的服务操作" value={agent.tools} options={catalog.tools.map((option) => ({ ...option, disabled: strategy.kind === "deterministic" && option.value === strategy.toolId }))} onChange={(next) => {
      const fixed = strategy.kind === "deterministic" && strategy.toolId ? strategy.toolId : undefined;
      const selected = fixed && !next.includes(fixed) ? [...next, fixed] : next;
      edit([], { ...agent, tools: selected, ...(agent.toolCache ? { toolCache: Object.fromEntries(Object.entries(agent.toolCache).filter(([key]) => selected.includes(key))) } : {}) });
    }} emptyText="还没有可用的服务操作。添加服务后可在这里选择。" />
    {strategy.kind === "deterministic" && <p className="text-sm text-muted-foreground">直接执行的服务操作会保持选中；要移除它，请先更换上方的完成方式或操作。</p>}
    <MultipleChoice label="允许使用的连接" value={agent.resources} options={catalog.connections} onChange={(v) => edit(["resources"], v)} emptyText="没有额外连接。AI 服务在上方单独选择。" />
    <Field label="用量与等待限制" description="留空使用默认限制。模型按自身计量单位统计用量，实际可处理的文字量因内容而异。"><div className="grid gap-3 sm:grid-cols-2">{budgets.map(([name, label, max]) => <NumberProperty key={name} label={label} value={agent.budget?.[name]} max={max} onChange={(v) => edit(["budget", name], v)} />)}</div></Field>
    <Field label="复用近期查询结果" description="仅适用于查询操作。同样的信息与连接可以在指定时间内复用；过期后重新查询。">
      {(agent.tools ?? []).map((key, index) => {
        const item = catalog.tools.find((candidate) => candidate.value === key);
        const policy = agent.toolCache?.[key];
        if (item?.effect === "write" && !policy) return null;
        const label = item?.label ?? `已保存的服务操作 ${index + 1}`;
        return <div key={key} className="flex flex-col gap-2"><label className="flex items-start gap-2 text-sm"><Checkbox aria-label={`复用 ${label}`} checked={!!policy} onCheckedChange={(checked) => edit(["toolCache", key], checked ? { ttlSeconds: 300 } : undefined)} />{label}</label>{policy && <NumberProperty label={`${label}：有效时间（秒）`} min={1} max={86400} value={policy.ttlSeconds} onChange={(v) => edit(["toolCache", key, "ttlSeconds"], v)} />}</div>;
      })}
      {!agent.tools?.length && <p className="text-sm text-muted-foreground">选好服务操作后，可设置查询结果的有效时间。</p>}
    </Field>
    <JsonSchemaEditor label="助手接收的信息" schema={agent.inputSchema} onChange={(v) => edit(["inputSchema"], v)} />
    <JsonSchemaEditor label="助手返回的内容" schema={agent.outputSchema} onChange={(v) => edit(["outputSchema"], v)} />
    <Button variant="outline" onClick={() => edit(["budget"], undefined)}>恢复默认用量与等待限制</Button>
  </FieldGroup>;
}
