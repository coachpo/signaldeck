import { Field, TextField, ChoiceField } from "@/components/shared/form-field";
import { Checkbox } from "@/components/ui/checkbox";
import type { JsonObject } from "@/lib/types/workflow-platform";

export type AuthoringChoice = { value: string; label: string; inputSchema?: JsonObject; outputSchema?: JsonObject; resultLinks?: { value: string; label: string }[]; effect?: string; disabled?: boolean };
export type AuthoringCatalog = { models: AuthoringChoice[]; connections: AuthoringChoice[]; tools: AuthoringChoice[] };
export type PropertyEdit = (path: string[], value: unknown) => void;

export function NumberProperty({ label, value, onChange, min = 1, max }: {
  label: string; value: number | undefined; onChange: (value: number | undefined) => void; min?: number; max?: number;
}) {
  return <div className="flex flex-col gap-1"><TextField label={label} type="number" value={value === undefined ? "" : String(value)} onChange={(v) => onChange(v === "" ? undefined : Number(v))} />
    {value !== undefined && (!Number.isInteger(value) || value < min || (max !== undefined && value > max)) && <p role="alert" className="text-xs text-destructive">请输入{max === undefined ? `不少于 ${min}` : `${min}–${max} 之间`}的整数。</p>}
  </div>;
}

export function SavedChoice({ label, value, options, onChange, missing = "已保存的选择（当前不可用）" }: {
  label: string; value: string; options: AuthoringChoice[]; onChange: (value: string) => void; missing?: string;
}) {
  return <ChoiceField label={label} value={value} onChange={onChange} options={value && !options.some((option) => option.value === value) ? [{ value, label: missing }, ...options] : options} />;
}

export function MultipleChoice({ label, value = [], options, onChange, emptyText = "暂无可选内容", missing = "已保存的选择（当前不可用）" }: {
  label: string; value?: string[]; options: AuthoringChoice[]; onChange: (value: string[]) => void; emptyText?: string; missing?: string;
}) {
  const choices: AuthoringChoice[] = [...options, ...value.filter((item) => !options.some((option) => option.value === item)).map((item, index) => ({ value: item, label: `${missing} ${index + 1}` }))];
  return <Field label={label}>{choices.length ? choices.map((option) => <label key={option.value} className="flex items-start gap-2 text-sm"><Checkbox aria-label={option.label} disabled={option.disabled} checked={value.includes(option.value)} onCheckedChange={(checked) => onChange(checked ? [...value, option.value] : value.filter((item) => item !== option.value))} /><span>{option.label}</span></label>) : <p className="text-sm text-muted-foreground">{emptyText}</p>}</Field>;
}
