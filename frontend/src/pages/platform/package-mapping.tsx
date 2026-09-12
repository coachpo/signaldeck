import { ChoiceField, Field, TextField } from "@/components/shared/form-field";
import { ValueEditor } from "@/components/platform-authoring/generated-form/value-editor";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import type { JsonObject } from "@/lib/types/workflow-platform";
import {
  asObject, changeConditionOperation, conditionOperations, defaultCondition,
  emptyLiteral, fieldLabel, renameMappingField, sourceForReference,
  type MappingSource,
} from "@/lib/platform-authoring/mapping-sources";

export type { MappingSource } from "@/lib/platform-authoring/mapping-sources";

type SourceProps = {
  label: string;
  value: string;
  onChange: (value: string) => void;
  sources: MappingSource[];
};

function SourcePath({ label, value, onChange, prefix, schema, depth = 1 }: {
  label: string; value: string; onChange: (value: string) => void;
  prefix: string; schema?: JsonObject; depth?: number;
}) {
  const remainder = value === prefix ? [] : value.slice(prefix.length + 1).split(".");
  const part = remainder[0];
  if (schema?.type === "object") {
    const properties = asObject(schema.properties);
    const child = part === undefined ? undefined : properties[part];
    return (
      <>
        <ChoiceField label={`${label} · 内容 ${depth}`} value={part === undefined ? "whole" : `field:${part}`}
          onChange={(next) => onChange(next === "whole" ? prefix : `${prefix}.${next.slice(6)}`)}
          options={[
            { value: "whole", label: "全部内容" },
            ...Object.entries(properties).map(([key, item]) => ({ value: `field:${key}`, label: fieldLabel(asObject(item), key) })),
            ...(part !== undefined && !Object.hasOwn(properties, part) ? [{ value: `field:${part}`, label: "已保存的内容（当前不可用）" }] : []),
          ]} />
        {part !== undefined && child !== undefined && <SourcePath label={label} value={value} onChange={onChange}
          prefix={`${prefix}.${part}`} schema={asObject(child)} depth={depth + 1} />}
      </>
    );
  }
  if (schema?.type === "array") {
    const position = part === undefined ? undefined : Number(part);
    return (
      <>
        <ChoiceField label={`${label} · 列表内容 ${depth}`} value={part === undefined ? "all" : "item"}
          onChange={(next) => onChange(next === "all" ? prefix : `${prefix}.0`)}
          options={[{ value: "all", label: "整个列表" }, { value: "item", label: "指定一项" }]} />
        {position !== undefined && Number.isInteger(position) && position >= 0 && <>
          <TextField label={`${label} · 第几项 ${depth}`} type="number" value={String(position + 1)}
            onChange={(next) => {
              const parsed = Number(next);
              if (next && Number.isInteger(parsed) && parsed > 0) onChange(`${prefix}.${parsed - 1}${remainder.length > 1 ? `.${remainder.slice(1).join(".")}` : ""}`);
            }} />
          <SourcePath label={label} value={value} onChange={onChange} prefix={`${prefix}.${part}`}
            schema={asObject(schema.items)} depth={depth + 1} />
        </>}
      </>
    );
  }
  return remainder.length ? <p className="text-sm text-muted-foreground">已保留保存的内容选择；重新选择来源后才会替换。</p> : null;
}

export function SourceChoice({ label, value, onChange, sources }: SourceProps) {
  const selected = sourceForReference(sources, value);
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <ChoiceField label={`${label} · 来源`} value={selected?.value ?? "__saved__"}
        onChange={onChange} options={[
          ...(!selected ? [{ value: "__saved__", label: value ? "已保存的来源（当前不可用）" : "请选择内容来源" }] : []),
          ...sources.map(({ value: reference, label: name }) => ({ value: reference, label: name })),
        ]} disabled={sources.length === 0} />
      {selected && <SourcePath label={label} value={value} onChange={onChange} prefix={selected.value} schema={selected.schema} />}
      {!sources.length && <p className="text-sm text-muted-foreground">尚无可选内容。请先设置输入信息或添加前面的步骤。</p>}
    </div>
  );
}

type MappingProps = {
  label?: string;
  value: JsonObject;
  onChange: (value: JsonObject) => void;
  sources: MappingSource[];
  targetSchema?: JsonObject;
};

export function MappingEditor({ label = "提供的内容", value, onChange, sources, targetSchema }: MappingProps) {
  const kind = ["ref", "value", "object", "array"].find((name) => Object.hasOwn(value, name)) ?? "saved";
  const fields = asObject(value.object);
  const properties = asObject(targetSchema?.properties);
  const remaining = Object.keys(properties).filter((key) => !Object.hasOwn(fields, key));
  const items = Array.isArray(value.array) ? value.array : [];
  const defaultMapping = (): JsonObject => ({ value: emptyLiteral(targetSchema) });
  const replaceKind = (next: string) => onChange(next === "ref" ? { ref: sources[0]?.value ?? "" }
    : next === "object" ? { object: {} } : next === "array" ? { array: [] } : defaultMapping());
  return (
    <Field label={label}>
      <ChoiceField label={`${label} · 提供方式`} value={kind} onChange={replaceKind} options={[
        { value: "ref", label: "使用已有信息" }, { value: "value", label: "填写固定内容" },
        { value: "object", label: "分别填写各项信息" }, { value: "array", label: "逐项组成列表" },
        ...(kind === "saved" ? [{ value: "saved", label: "已保存的设置" }] : []),
      ]} />
      {kind === "ref" && <>
        <SourceChoice label={label} value={String(value.ref)} onChange={(ref) => onChange({ ...value, ref })} sources={sources} />
        <label className="flex items-center gap-2 text-sm">
          <Checkbox checked={Object.hasOwn(value, "onMissing")} onCheckedChange={(checked) => {
            if (checked === true) onChange({ ...value, onMissing: defaultMapping() });
            else { const { onMissing: _removed, ...rest } = value; onChange(rest); }
          }} />来源没有内容时使用备用内容
        </label>
        {Object.hasOwn(value, "onMissing") && <MappingEditor label={`${label} · 备用内容`} value={asObject(value.onMissing)}
          onChange={(onMissing) => onChange({ ...value, onMissing })} sources={sources} targetSchema={targetSchema} />}
      </>}
      {kind === "value" && <ValueEditor label={`${label} · 固定内容`} schema={targetSchema} value={value.value}
        onChange={(content) => onChange({ ...value, value: content })} />}
      {kind === "object" && <>
        {Object.entries(fields).map(([key, mapping], index) => <div key={index} className="flex flex-col gap-3 border-l border-border pl-3">
          {targetSchema?.type === "object" ? <ChoiceField label={`${label} · 信息 ${index + 1}`} value={key}
            onChange={(name) => onChange({ ...value, object: renameMappingField(fields, key, name) })}
            options={[key, ...remaining].map((name) => ({ value: name, label: fieldLabel(asObject(properties[name]), name) }))} />
            : <TextField label={`${label} · 信息名称 ${index + 1}`} value={key}
              onChange={(name) => onChange({ ...value, object: renameMappingField(fields, key, name) })} />}
          <MappingEditor label={fieldLabel(asObject(properties[key]), key || `信息 ${index + 1}`)} value={asObject(mapping)} sources={sources}
            targetSchema={properties[key] === undefined ? undefined : asObject(properties[key])}
            onChange={(content) => onChange({ ...value, object: { ...fields, [key]: content } })} />
          <Button type="button" variant="outline" aria-label={`移除${label}的信息 ${index + 1}`} onClick={() => {
            const { [key]: _removed, ...rest } = fields; onChange({ ...value, object: rest });
          }}>移除这项信息</Button>
        </div>)}
        <Button type="button" variant="outline" disabled={targetSchema?.type === "object" && !remaining.length} onClick={() => {
          let name = remaining[0] ?? "新信息";
          for (let index = 2; Object.hasOwn(fields, name); index++) name = `新信息 ${index}`;
          onChange({ ...value, object: { ...fields, [name]: { value: emptyLiteral(asObject(properties[name])) } } });
        }}>添加信息</Button>
      </>}
      {kind === "array" && <>
        {items.map((item, index) => <div key={index} className="flex flex-col gap-2 border-l border-border pl-3">
          <MappingEditor label={`${label} · 第 ${index + 1} 项`} value={asObject(item)} sources={sources}
            targetSchema={targetSchema?.items === undefined ? undefined : asObject(targetSchema.items)}
            onChange={(content) => onChange({ ...value, array: items.map((old, at) => at === index ? content : old) })} />
          <div className="flex flex-wrap gap-2">
            <Button type="button" variant="outline" disabled={index === 0} aria-label={`${label}第 ${index + 1} 项上移`} onClick={() => {
              const moved = [...items]; [moved[index - 1], moved[index]] = [moved[index], moved[index - 1]]; onChange({ ...value, array: moved });
            }}>上移</Button>
            <Button type="button" variant="outline" aria-label={`移除${label}第 ${index + 1} 项`}
              onClick={() => onChange({ ...value, array: items.filter((_, at) => at !== index) })}>移除</Button>
          </div>
        </div>)}
        <Button type="button" variant="outline" onClick={() => onChange({ ...value, array: [...items, { value: emptyLiteral(asObject(targetSchema?.items)) }] })}>添加一项</Button>
      </>}
    </Field>
  );
}

export function ConditionEditor({ label = "执行条件", value, onChange, sources }: Omit<MappingProps, "targetSchema">) {
  const operation = typeof value.op === "string" ? value.op : "saved";
  const args = Array.isArray(value.args) ? value.args : [];
  const group = ["all", "any", "not"].includes(operation);
  const updateArg = (index: number, next: JsonObject) => onChange({ ...value, args: args.map((arg, at) => at === index ? next : arg) });
  return (
    <Field label={label}>
      <ChoiceField label={`${label} · 判断方式`} value={operation} onChange={(next) => onChange(changeConditionOperation(value, next))}
        options={[...conditionOperations, ...(!conditionOperations.some((item) => item.value === operation) ? [{ value: operation, label: "已保存的条件" }] : [])]} />
      {args.map((arg, index) => <div key={index} className="flex flex-col gap-2 border-l border-border pl-3">
        {group ? <ConditionEditor label={`${label} · 条件 ${index + 1}`} value={asObject(arg)} sources={sources} onChange={(next) => updateArg(index, next)} />
          : <MappingEditor label={`${label} · ${operation === "exists" ? "要检查的内容" : index === 0 ? "比较的内容" : "比较目标"}`}
            value={asObject(arg)} sources={sources} onChange={(next) => updateArg(index, next)} />}
        {["all", "any"].includes(operation) && <Button type="button" variant="outline" disabled={args.length === 1}
          aria-label={`移除${label}条件 ${index + 1}`} onClick={() => onChange({ ...value, args: args.filter((_, at) => at !== index) })}>移除条件</Button>}
      </div>)}
      {["all", "any"].includes(operation) && <Button type="button" variant="outline" onClick={() => onChange({ ...value, args: [...args, defaultCondition()] })}>添加条件</Button>}
    </Field>
  );
}
