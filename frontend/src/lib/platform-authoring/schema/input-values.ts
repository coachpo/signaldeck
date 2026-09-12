import type { Json, JsonObject } from "@/lib/types/workflow-platform";

export const valueTypeLabels: Record<string, string> = {
  object: "一组字段",
  array: "列表",
  string: "文字",
  integer: "整数",
  number: "数字",
  boolean: "是或否",
  null: "空值",
};

export function asInputSchema(value: Json | undefined): JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value
    : {};
}

export function inputLabel(schema: JsonObject, fallback: string): string {
  return typeof schema.title === "string" && schema.title.trim()
    ? schema.title
    : fallback;
}

export function orderedInputKeys(
  keys: string[],
  path: string[],
  hints: readonly { ref: string }[],
): string[] {
  const order = (key: string) => {
    const ref = ["workflow", "input", ...path, key].join(".");
    const index = hints.findIndex(
      (hint) => hint.ref === ref || hint.ref.startsWith(`${ref}.`),
    );
    return index < 0 ? Number.POSITIVE_INFINITY : index;
  };
  return [...keys].sort((left, right) => order(left) - order(right));
}

export function valueType(value: Json | undefined): string {
  if (value === null) return "null";
  if (Array.isArray(value)) return "array";
  return typeof value === "undefined" ? "string" : typeof value;
}

export function inputValuesEqual(
  left: Json | undefined,
  right: Json | undefined,
): boolean {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right))
    return (
      left.length === right.length &&
      left.every((item, index) => inputValuesEqual(item, right[index]))
    );
  if (
    left &&
    right &&
    typeof left === "object" &&
    typeof right === "object" &&
    !Array.isArray(left) &&
    !Array.isArray(right)
  )
    return (
      Object.keys(left).length === Object.keys(right).length &&
      Object.keys(left).every(
        (key) =>
          Object.hasOwn(right, key) && inputValuesEqual(left[key], right[key]),
      )
    );
  return false;
}

/** Only call when creating a new value, never to normalize an existing draft. */
export function newInputValue(schema: JsonObject, useDefault = true): Json {
  if (
    useDefault &&
    schema["x-signaldeck-schema"] === "signaldeck.schema/2" &&
    Object.hasOwn(schema, "default")
  )
    return structuredClone(schema.default);
  if (Object.hasOwn(schema, "const")) return structuredClone(schema.const);
  if (Array.isArray(schema.enum) && schema.enum.length)
    return structuredClone(schema.enum[0]);
  if (Array.isArray(schema.anyOf) && schema.anyOf.length)
    return newInputValue(asInputSchema(schema.anyOf[0]), useDefault);
  const kind = Array.isArray(schema.type) ? schema.type[0] : schema.type;
  if (kind === "object") {
    const required = Array.isArray(schema.required) ? schema.required : [];
    return Object.fromEntries(
      Object.entries(asInputSchema(schema.properties))
        .filter(([key, entry]) => {
          const field = asInputSchema(entry);
          return (
            required.includes(key) ||
            (useDefault &&
              field["x-signaldeck-schema"] === "signaldeck.schema/2" &&
              Object.hasOwn(field, "default"))
          );
        })
        .map(([key, entry]) => [
          key,
          newInputValue(asInputSchema(entry), useDefault),
        ]),
    );
  }
  if (kind === "array") return [];
  if (kind === "integer" || kind === "number") return 0;
  if (kind === "boolean") return false;
  if (kind === "null") return null;
  return "";
}

export type InputValueIssue = {
  label: string;
  message: string;
  path: string[];
};

function typeMatches(kind: Json | undefined, value: Json | undefined): boolean {
  if (Array.isArray(kind)) return kind.some((item) => typeMatches(item, value));
  if (kind === "integer")
    return typeof value === "number" && Number.isInteger(value);
  return typeof kind !== "string" || kind === valueType(value);
}

/** Browser feedback mirrors supported value rules; server validation remains authoritative. */
export function inputValueIssues(
  schema: JsonObject,
  value: Json | undefined,
  label = "输入内容",
  path: string[] = [],
): InputValueIssue[] {
  const title = inputLabel(schema, label);
  const issue = (message: string) => ({ label: title, message, path });
  if (value === undefined) return [issue("请填写此项。")];
  if (Array.isArray(schema.anyOf)) {
    const alternatives = schema.anyOf.map((item) =>
      inputValueIssues(asInputSchema(item), value, title, path),
    );
    if (alternatives.some((items) => items.length === 0)) return [];
    return alternatives.sort((a, b) => a.length - b.length)[0] ?? [];
  }
  if (!typeMatches(schema.type, value)) {
    const kinds = Array.isArray(schema.type) ? schema.type : [schema.type];
    return [
      issue(
        `请填写${kinds.map((kind) => valueTypeLabels[String(kind)] ?? "所需内容").join("或")}。`,
      ),
    ];
  }
  if (typeof value === "number" && !Number.isFinite(value))
    return [issue("请填写有效数字。")];
  if (Object.hasOwn(schema, "const") && !inputValuesEqual(schema.const, value))
    return [issue("请使用此项规定的固定内容。")];
  if (
    Array.isArray(schema.enum) &&
    !schema.enum.some((option) => inputValuesEqual(option, value))
  )
    return [issue("请选择列表中的一个选项。")];
  const issues: InputValueIssue[] = [];
  const bound = (
    key: string,
    actual: number,
    matches: (actual: number, limit: number) => boolean,
    message: (limit: number) => string,
  ) => {
    const limit = schema[key];
    if (typeof limit === "number" && !matches(actual, limit))
      issues.push(issue(message(limit)));
  };
  if (typeof value === "string") {
    bound(
      "minLength",
      [...value].length,
      (a, b) => a >= b,
      (n) => `请至少填写 ${n} 个字符。`,
    );
    bound(
      "maxLength",
      [...value].length,
      (a, b) => a <= b,
      (n) => `请勿超过 ${n} 个字符。`,
    );
  }
  if (typeof value === "number") {
    bound(
      "minimum",
      value,
      (a, b) => a >= b,
      (n) => `请填写不小于 ${n} 的数字。`,
    );
    bound(
      "maximum",
      value,
      (a, b) => a <= b,
      (n) => `请填写不大于 ${n} 的数字。`,
    );
    bound(
      "exclusiveMinimum",
      value,
      (a, b) => a > b,
      (n) => `请填写大于 ${n} 的数字。`,
    );
    bound(
      "exclusiveMaximum",
      value,
      (a, b) => a < b,
      (n) => `请填写小于 ${n} 的数字。`,
    );
    bound(
      "multipleOf",
      value,
      (a, b) => Math.abs(a / b - Math.round(a / b)) < 1e-10,
      (n) => `请以 ${n} 为间隔填写。`,
    );
  }
  if (Array.isArray(value)) {
    bound(
      "minItems",
      value.length,
      (a, b) => a >= b,
      (n) => `请至少添加 ${n} 项。`,
    );
    bound(
      "maxItems",
      value.length,
      (a, b) => a <= b,
      (n) => `最多添加 ${n} 项。`,
    );
    if (
      schema.uniqueItems === true &&
      value.some((item, index) =>
        value
          .slice(0, index)
          .some((previous) => inputValuesEqual(item, previous)),
      )
    )
      issues.push(issue("列表中存在重复项目，请修改或移除重复项。"));
    value.forEach((item, index) =>
      issues.push(
        ...inputValueIssues(
          asInputSchema(schema.items),
          item,
          `第 ${index + 1} 项`,
          [...path, String(index)],
        ),
      ),
    );
  } else if (value && typeof value === "object") {
    const fields = asInputSchema(schema.properties);
    const required = Array.isArray(schema.required) ? schema.required : [];
    bound(
      "minProperties",
      Object.keys(value).length,
      (a, b) => a >= b,
      (n) => `请至少填写 ${n} 个字段。`,
    );
    bound(
      "maxProperties",
      Object.keys(value).length,
      (a, b) => a <= b,
      (n) => `最多填写 ${n} 个字段。`,
    );
    Object.entries(fields).forEach(([key, field]) => {
      if (Object.hasOwn(value, key) || required.includes(key))
        issues.push(
          ...inputValueIssues(asInputSchema(field), value[key], key, [
            ...path,
            key,
          ]),
        );
    });
    if (schema.type === undefined)
      Object.keys(value)
        .filter((key) => !Object.hasOwn(fields, key))
        .forEach((key) =>
          issues.push(...inputValueIssues({}, value[key], key, [...path, key])),
        );
    if (schema.type === "object")
      Object.keys(value)
        .filter((key) => !Object.hasOwn(fields, key))
        .forEach((key) =>
          issues.push({
            label: key,
            path: [...path, key],
            message: "当前任务不再使用此项。内容仍保留，请核对后移除。",
          }),
        );
  }
  return issues;
}
