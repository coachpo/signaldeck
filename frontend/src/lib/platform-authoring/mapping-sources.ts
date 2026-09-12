import type { Json, JsonObject } from "@/lib/types/workflow-platform";

export type MappingSource = { value: string; label: string; schema?: JsonObject };

export function asObject(value: Json | undefined): JsonObject {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

export function fieldLabel(schema: JsonObject | undefined, fallback: string): string {
  return typeof schema?.title === "string" && schema.title.trim() ? schema.title : fallback;
}

export function sourceForReference(sources: MappingSource[], reference: string): MappingSource | undefined {
  return sources
    .filter((source) => reference === source.value || reference.startsWith(`${source.value}.`))
    .sort((left, right) => right.value.length - left.value.length)[0];
}

export function sourceSchema(source: MappingSource, reference: string): JsonObject | undefined {
  let schema = source.schema;
  const suffix = reference.slice(source.value.length).replace(/^\./, "");
  for (const part of suffix ? suffix.split(".") : []) {
    if (schema?.type === "object") {
      const child = asObject(schema.properties)[part];
      schema = child && typeof child === "object" && !Array.isArray(child) ? child : undefined;
    } else if (schema?.type === "array" && /^\d+$/.test(part)) {
      schema = asObject(schema.items);
    } else return undefined;
  }
  return schema;
}

export function firstReference(sources: MappingSource[], types?: string[], childrenOnly = false, excluded: string[] = []): string | undefined {
  function visit(schema: JsonObject | undefined, reference: string, isRoot: boolean): string | undefined {
    if ((!childrenOnly || !isRoot) && (!types || types.includes(String(schema?.type))) && !excluded.includes(reference)) return reference;
    if (schema?.type === "object") {
      for (const [key, child] of Object.entries(asObject(schema.properties))) {
        const found = visit(asObject(child), `${reference}.${key}`, false);
        if (found) return found;
      }
    }
    if (schema?.type === "array") {
      for (let index = 0; index <= excluded.length; index++) {
        const found = visit(asObject(schema.items), `${reference}.${index}`, false);
        if (found) return found;
      }
    }
    return undefined;
  }
  for (const source of sources) {
    const found = visit(source.schema, source.value, true);
    if (found) return found;
  }
  return undefined;
}

export function emptyLiteral(schema?: JsonObject): Json {
  const type = Array.isArray(schema?.type) ? schema.type[0] : schema?.type;
  if (type === "object") return {};
  if (type === "array") return [];
  if (type === "number" || type === "integer") return 0;
  if (type === "boolean") return false;
  if (type === "null") return null;
  return "";
}

export function renameMappingField(fields: JsonObject, from: string, to: string): JsonObject {
  if (from !== to && Object.hasOwn(fields, to)) return fields;
  return Object.fromEntries(Object.entries(fields).map(([key, value]) => [key === from ? to : key, value]));
}

export const conditionOperations = [
  { value: "eq", label: "等于" }, { value: "ne", label: "不等于" },
  { value: "lt", label: "小于" }, { value: "lte", label: "小于或等于" },
  { value: "gt", label: "大于" }, { value: "gte", label: "大于或等于" },
  { value: "exists", label: "已提供内容" },
  { value: "all", label: "同时满足全部条件" }, { value: "any", label: "满足任一条件" },
  { value: "not", label: "不满足以下条件" },
];

export function defaultCondition(): JsonObject {
  return { op: "eq", args: [{ value: "" }, { value: "" }] };
}

export function changeConditionOperation(condition: JsonObject, operation: string): JsonObject {
  const args = Array.isArray(condition.args) ? condition.args : [];
  const wasGroup = ["all", "any", "not"].includes(String(condition.op));
  const isGroup = ["all", "any", "not"].includes(operation);
  const candidates = wasGroup === isGroup ? args : [];
  const count = operation === "not" || operation === "exists" ? 1 : isGroup ? Math.max(1, candidates.length) : 2;
  return {
    op: operation,
    args: Array.from({ length: count }, (_, index) => candidates[index] ?? (isGroup ? defaultCondition() : { value: "" })),
  };
}
