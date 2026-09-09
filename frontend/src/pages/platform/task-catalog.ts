import type { Json, JsonObject, WorkflowPackage } from "@/lib/types/workflow-platform";
import { initialParameters, isJsonObject } from "@/lib/platform-authoring/parameter-values";
import { createLaunchInputState } from "@/lib/platform-authoring/schema/launch-input-state";

export function supportsTaskForm(schema: JsonObject) {
  return createLaunchInputState(schema).schemaSupported;
}

/** Initial values are used only when creating a new input draft. */
export function taskDefaults(schema: JsonObject): Json {
  return initialParameters(schema);
}

export function availableTasks(packages: WorkflowPackage[]) {
  return packages.flatMap((pkg) =>
    Object.entries(pkg.definition.workflows).map(([workflowKey, workflow]) => ({
      packageKey: pkg.key,
      workflowKey,
      title: workflow.name || workflowKey,
      description: workflow.description ?? pkg.definition.metadata.description ?? "",
      pkg,
      workflow,
      supported: supportsTaskForm(workflow.inputSchema),
    })),
  );
}

/** Adds declared schema constraints to the existing schema/type validation. */
export function taskConstraintErrors(
  schema: JsonObject,
  value: Json,
  path = "parameters",
): Record<string, string> {
  const errors: Record<string, string> = {};
  if (typeof value === "string") {
    if (typeof schema.minLength === "number" && [...value].length < schema.minLength)
      errors[path] = `请至少填写 ${schema.minLength} 个字符。`;
    if (typeof schema.maxLength === "number" && [...value].length > schema.maxLength)
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
