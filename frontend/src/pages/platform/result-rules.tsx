import type { JsonObject } from "@/lib/types/workflow-platform";
import { asObject, conditionOperations, fieldLabel, sourceForReference, type MappingSource } from "@/lib/platform-authoring/mapping-sources";
import { ResultValue } from "./result-content";

function referenceLabel(reference: string, sources: MappingSource[]) {
  const source = sourceForReference(sources, reference);
  if (!source) return "已保存的内容选择";
  const labels = [source.label];
  let schema = source.schema;
  for (const part of reference.slice(source.value.length).split(".").filter(Boolean)) {
    if (schema?.type === "array") {
      labels.push(`第 ${Number(part) + 1} 项`);
      schema = asObject(schema.items);
    } else {
      const properties = asObject(schema?.properties);
      const index = Object.keys(properties).indexOf(part);
      schema = asObject(properties[part]);
      labels.push(fieldLabel(schema, index >= 0 ? `第 ${index + 1} 项内容` : "已保存的内容选择"));
    }
  }
  return labels.join(" › ");
}

export function RecordedMapping({ value, sources, targetSchema }: { value: JsonObject; sources: MappingSource[]; targetSchema?: JsonObject }) {
  if (Object.hasOwn(value, "value")) return <ResultValue value={value.value} schema={targetSchema} />;
  if (typeof value.ref === "string") return <div className="flex flex-col gap-1"><p>{referenceLabel(value.ref, sources)}</p>
    {Object.hasOwn(value, "onMissing") && <div><p className="text-muted-foreground">未提供时使用：</p><RecordedMapping value={asObject(value.onMissing)} sources={sources} targetSchema={targetSchema} /></div>}
  </div>;
  if (value.object) return <dl className="flex flex-col gap-2">{Object.entries(asObject(value.object)).map(([key, child], index) => {
    const childSchema = asObject(asObject(targetSchema?.properties)[key]);
    return <div key={key}><dt className="text-muted-foreground">{fieldLabel(childSchema, `信息 ${index + 1}`)}</dt><dd><RecordedMapping value={asObject(child)} sources={sources} targetSchema={childSchema} /></dd></div>;
  })}</dl>;
  if (Array.isArray(value.array)) return <ol className="list-decimal pl-5">{value.array.map((child, index) => <li key={index}><RecordedMapping value={asObject(child)} sources={sources} targetSchema={asObject(targetSchema?.items)} /></li>)}</ol>;
  return <p>已保存的内容设置</p>;
}

export function RecordedCondition({ value, sources }: { value: JsonObject; sources: MappingSource[] }) {
  const operation = String(value.op);
  const args = Array.isArray(value.args) ? value.args : [];
  const label = conditionOperations.find((choice) => choice.value === operation)?.label ?? "已保存的执行条件";
  const group = ["all", "any", "not"].includes(operation);
  return <div className="flex flex-col gap-2">
    <p className="font-medium">{label}</p>
    <ol className="flex flex-col gap-2 border-l border-border pl-3">{args.map((arg, index) => <li key={index}>
      {group ? <RecordedCondition value={asObject(arg)} sources={sources} /> : <RecordedMapping value={asObject(arg)} sources={sources} />}
    </li>)}</ol>
  </div>;
}
