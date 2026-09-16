import { useState } from "react";
import { ChoiceField, Field, FieldGroup, TextField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import type { AgentDefinition, ExecutionOptions, WorkflowDefinition } from "@/lib/types/workflow-platform";

type Budget = NonNullable<AgentDefinition["budget"]>;
type BudgetKey = keyof Budget;
const fields: { key: BudgetKey; label: string; max?: number; initial: number; modes?: { value: string; label: string }[] }[] = [
  { key: "maxTokens", label: "累计模型用量", initial: 100000, modes: [{ value: "unlimited", label: "不设限" }] },
  { key: "maxOutputTokens", label: "单次输出", initial: 4096, modes: [{ value: "auto", label: "按剩余额度" }, { value: "provider_default", label: "由模型服务决定" }] },
  { key: "maxModelRequests", label: "模型处理次数", max: 1000, initial: 12 },
  { key: "maxToolCalls", label: "服务操作次数", max: 10000, initial: 32 },
  { key: "deadlineSeconds", label: "最长执行时间（秒）", max: 86400, initial: 300 },
  { key: "maxParallelTools", label: "同时执行的操作数", max: 128, initial: 4 },
];

export function BudgetControls({ value = {}, onChange, disabled = false, inheritLabel = "沿用默认", mixedFields = [], onFieldChange }: {
  value?: Budget; onChange: (value: Budget) => void; disabled?: boolean; inheritLabel?: string; mixedFields?: BudgetKey[];
  onFieldChange?: (key: BudgetKey, value: Budget[BudgetKey] | undefined) => void;
}) {
  function change(key: BudgetKey, next: Budget[BudgetKey] | undefined) {
    if (onFieldChange) return onFieldChange(key, next);
    const budget = { ...value };
    if (next === undefined) delete budget[key];
    else Object.assign(budget, { [key]: next });
    onChange(budget);
  }
  return <FieldGroup>{fields.map(({ key, label, max, initial, modes = [] }) => {
    const current = value[key];
    const invalid = typeof current === "number" && (!Number.isSafeInteger(current) || current < 1 || (max !== undefined && current > max));
    return <Field key={key} label={label} invalid={invalid}>
      <ChoiceField label={`${label}方式`} disabled={disabled} value={mixedFields.includes(key) ? "mixed" : current === undefined ? "inherit" : typeof current === "number" ? "limited" : current}
        options={[...(mixedFields.includes(key) ? [{ value: "mixed", label: "各助手设置不同" }] : []), { value: "inherit", label: inheritLabel }, { value: "limited", label: "指定额度" }, ...modes]}
        onChange={(mode) => mode !== "mixed" && change(key, mode === "inherit" ? undefined : mode === "limited" ? initial : mode as Budget[BudgetKey])} />
      {typeof current === "number" && <TextField label={`${label}数值`} disabled={disabled} type="number" value={String(current)} onChange={(raw) => change(key, raw === "" ? undefined : Number(raw))} />}
      {invalid && <p role="alert" className="text-sm text-destructive">请输入{max ? `1–${max} 之间` : "大于 0"}的整数。</p>}
    </Field>;
  })}</FieldGroup>;
}

export function TaskBudgetControls({ agents, workflow, value, onChange, disabled = false }: {
  agents: Record<string, AgentDefinition>; workflow: WorkflowDefinition; value?: ExecutionOptions;
  onChange: (value: ExecutionOptions) => void; disabled?: boolean;
}) {
  const [selected, setSelected] = useState("all");
  const keys = [...new Set(Object.values(workflow.nodes).map((node) => node.uses))].filter((key) => agents[key]);
  const overrides = value?.agentBudgets ?? {};
  const selectedKey = selected.startsWith("agent:") ? selected.slice(6) : null;
  const target = selectedKey !== null && keys.includes(selectedKey) ? selectedKey : null;
  const common = target === null ? Object.fromEntries(fields.flatMap(({ key }) => {
    const first = overrides[keys[0]]?.[key];
    return first !== undefined && keys.every((agent) => overrides[agent]?.[key] === first) ? [[key, first]] : [];
  })) as Budget : overrides[target] ?? {};
  const mixedFields = target === null ? fields.filter(({ key }) => keys.some((agent) => overrides[agent]?.[key] !== overrides[keys[0]]?.[key])).map(({ key }) => key) : [];
  if (!keys.length) return null;
  function change(key: BudgetKey, next: Budget[BudgetKey] | undefined) {
    const budgets = { ...overrides };
    for (const agent of target === null ? keys : [target]) {
      const budget = { ...budgets[agent] };
      if (next === undefined) delete budget[key];
      else Object.assign(budget, { [key]: next });
      if (Object.keys(budget).length) budgets[agent] = budget;
      else delete budgets[agent];
    }
    onChange({ ...value, agentBudgets: budgets });
  }
  return <details className="flex flex-col gap-3">
    <summary className="cursor-pointer font-medium">用量与时间限制 · {Object.keys(overrides).length ? "已调整本次设置" : "使用工作流默认设置"}</summary>
    <div className="flex flex-col gap-4 pt-4">
      <p className="text-sm text-muted-foreground">限制分别用于每次助手执行；同一助手用于多个步骤时分别计算。统一设置不会形成任务共享额度。累计用量在响应后核验，一次回答可能超过停止线。</p>
      <ChoiceField label="调整范围" value={target === null ? "all" : `agent:${target}`} disabled={disabled} onChange={setSelected} options={[{ value: "all", label: "统一应用到所有助手" }, ...keys.map((key, index) => ({ value: `agent:${key}`, label: agents[key].name || `助手 ${index + 1}` }))]} />
      {target === null && <p className="text-sm text-muted-foreground">每次只应用修改的项目；各助手不同的设置请逐项查看。</p>}
      <BudgetControls value={common} onChange={() => {}} onFieldChange={change} disabled={disabled} inheritLabel="沿用工作流默认" mixedFields={mixedFields} />
      <p className="text-sm text-muted-foreground">由模型服务决定时，平台不指定单次输出长度；模型服务仍有自身限制。清空数值会恢复默认设置。启动前的检查会显示最终生效值。</p>
      <Button type="button" variant="outline" disabled={disabled} onClick={() => onChange({ ...value, agentBudgets: {} })}>恢复工作流默认设置</Button>
    </div>
  </details>;
}
