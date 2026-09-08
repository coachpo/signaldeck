import type {
  Json,
  JsonObject,
  WorkflowPackage,
} from "@/lib/types/workflow-platform";
import {
  isJsonObject,
  initialParameters,
} from "@/lib/platform-authoring/parameter-values";
export interface TaskDescriptor {
  packageKey: string;
  workflowKey: string;
  title: string;
  description: string;
  fields: Record<string, string>;
}
export const taskDescriptors: TaskDescriptor[] = [
  {
    packageKey: "tradingagents_advisory_research",
    workflowKey: "research",
    title: "市场研究",
    description: "分析关注的市场对象、变化与风险，生成研究报告。",
    fields: { symbols: "array", question: "string", includeRisk: "boolean" },
  },
  {
    packageKey: "digital_oracle_researcher",
    workflowKey: "research",
    title: "综合资料研究",
    description: "围绕一个问题汇集多个来源，形成可追溯的研究报告。",
    fields: { question: "string" },
  },
  {
    packageKey: "research_notes",
    workflowKey: "research",
    title: "整理笔记",
    description: "结合已有笔记整理资料，并保存新的笔记。",
    fields: {
      title: "string",
      text: "string",
      query: "string",
      summarize: "boolean",
    },
  },
  {
    packageKey: "research_notes",
    workflowKey: "capture",
    title: "保存原文",
    description: "直接保存标题与原文，不需要模型服务。",
    fields: { title: "string", text: "string" },
  },
];
export function taskDescriptor(packageKey: string, workflowKey: string) {
  return taskDescriptors.find(
    (t) => t.packageKey === packageKey && t.workflowKey === workflowKey,
  );
}
export function supportsTaskForm(
  task: TaskDescriptor | undefined,
  schema: JsonObject,
) {
  if (
    !task ||
    schema.type !== "object" ||
    !isJsonObject(schema.properties ?? null)
  )
    return false;
  const fields = Object.entries(schema.properties as JsonObject);
  return (
    fields.length === Object.keys(task.fields).length &&
    fields.every(
      ([key, spec]) =>
        isJsonObject(spec) &&
        spec.type === task.fields[key] &&
        (spec.type !== "array" ||
          (isJsonObject(spec.items ?? null) &&
            (spec.items as JsonObject).type === "string")),
    )
  );
}
export function taskDefaults(schema: JsonObject): Json {
  // API schema projections may include default:null for non-nullable fields.
  // Such a placeholder is not an authored runtime default.
  function defaults(node: JsonObject): JsonObject {
    const result = { ...node };
    if (
      result.default === null &&
      result.type !== "null" &&
      !(Array.isArray(result.type) && result.type.includes("null"))
    )
      delete result.default;
    if (isJsonObject(result.properties ?? null))
      result.properties = Object.fromEntries(
        Object.entries(result.properties as JsonObject).map(([key, item]) => [
          key,
          isJsonObject(item) ? defaults(item) : item,
        ]),
      );
    if (isJsonObject(result.items ?? null))
      result.items = defaults(result.items as JsonObject);
    return result;
  }
  const clean = defaults(schema);
  function seed(node: JsonObject): Json {
    if (Object.hasOwn(node, "default")) return structuredClone(node.default);
    if (node.type === "object" && isJsonObject(node.properties ?? null))
      return Object.fromEntries(
        Object.entries(node.properties as JsonObject)
          .filter(
            ([key, spec]) =>
              (Array.isArray(node.required) && node.required.includes(key)) ||
              (isJsonObject(spec) && Object.hasOwn(spec, "default")),
          )
          .map(([key, spec]) => [key, isJsonObject(spec) ? seed(spec) : null]),
      );
    if (node.type === "array") return [];
    if (node.type === "boolean") return false;
    if (node.type === "number" || node.type === "integer") return 0;
    if (node.type === "string") return "";
    return null;
  }
  const parsed = initialParameters(clean);
  const value =
    parsed === null && clean.type === "object" ? seed(clean) : parsed;
  if (!isJsonObject(value)) return value;
  return {
    ...value,
    ...(Object.hasOwn(value, "includeRisk") &&
    !isJsonObject(schema.default ?? null) &&
    isJsonObject(schema.properties ?? null) &&
    isJsonObject((schema.properties as JsonObject).includeRisk) &&
    typeof ((schema.properties as JsonObject).includeRisk as JsonObject)
      .default !== "boolean"
      ? { includeRisk: true }
      : {}),
  };
}
export function availableTasks(packages: WorkflowPackage[]) {
  return taskDescriptors.flatMap((task) => {
    const pkg = packages.find((p) => p.key === task.packageKey);
    const workflow = pkg?.definition.workflows[task.workflowKey];
    return pkg && workflow
      ? [
          {
            ...task,
            pkg,
            workflow,
            supported: supportsTaskForm(task, workflow.inputSchema),
          },
        ]
      : [];
  });
}

/** Adds business-field constraints to the existing schema/type validation. */
export function taskConstraintErrors(
  schema: JsonObject,
  value: Json,
  path = "parameters",
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (typeof value === "string") {
    if (typeof schema.minLength === "number" && value.length < schema.minLength)
      errors[path] = `请至少填写 ${schema.minLength} 个字符。`;
    if (typeof schema.maxLength === "number" && value.length > schema.maxLength)
      errors[path] = `请勿超过 ${schema.maxLength} 个字符。`;
  }
  if (Array.isArray(value)) {
    if (typeof schema.minItems === "number" && value.length < schema.minItems)
      errors[path] = `请至少添加 ${schema.minItems} 项。`;
    if (typeof schema.maxItems === "number" && value.length > schema.maxItems)
      errors[path] = `最多添加 ${schema.maxItems} 项。`;
    if (isJsonObject(schema.items ?? null))
      value.forEach((item, index) =>
        Object.assign(
          errors,
          taskConstraintErrors(
            schema.items as JsonObject,
            item,
            `${path}.${index}`,
          ),
        ),
      );
  }
  if (isJsonObject(value) && isJsonObject(schema.properties ?? null))
    Object.entries(schema.properties as JsonObject).forEach(([key, spec]) => {
      if (isJsonObject(spec) && Object.hasOwn(value, key))
        Object.assign(
          errors,
          taskConstraintErrors(spec, value[key], `${path}.${key}`),
        );
    });
  return errors;
}
