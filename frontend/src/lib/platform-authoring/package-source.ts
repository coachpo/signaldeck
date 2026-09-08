import { parseDocument, stringify } from "yaml";
import type {
  JsonObject,
  PackageDefinition,
} from "@/lib/types/workflow-platform";
export function parseDefinition(source: string): PackageDefinition {
  const document = parseDocument(source, { uniqueKeys: true });
  if (document.errors.length) throw new Error(document.errors[0].message);
  const value: unknown = document.toJS({ maxAliasCount: 0 });
  if (
    !value ||
    typeof value !== "object" ||
    !("apiVersion" in value) ||
    value.apiVersion !== "signaldeck.workflowPackage/v2" ||
    !("metadata" in value) ||
    !("agents" in value) ||
    !("workflows" in value)
  )
    throw new Error(
      "A v2 Workflow Package requires metadata, agents and workflows.",
    );
  const object = value as Record<string, unknown>;
  for (const section of ["metadata", "agents", "workflows"])
    if (
      !object[section] ||
      typeof object[section] !== "object" ||
      Array.isArray(object[section])
    )
      throw new Error(`${section} must be an object.`);
  const metadata = object.metadata as Record<string, unknown>;
  if (typeof metadata.key !== "string" || typeof metadata.name !== "string")
    throw new Error("Package key and name must be strings.");
  return value as PackageDefinition;
}
export function updateSource(
  source: string,
  path: string[],
  value: unknown,
): string {
  parseDefinition(source);
  const document = parseDocument(source, { uniqueKeys: true });
  if (value === undefined) document.deleteIn(path);
  else document.setIn(path, value);
  return document.toString();
}
export function parseObject(value: string): JsonObject {
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch {
    throw new Error("Enter a valid JSON object.");
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
    throw new Error("Enter a JSON object.");
  return parsed as JsonObject;
}
export const initialPackageSource = stringify({
  apiVersion: "signaldeck.workflowPackage/v2",
  metadata: { key: "new-workflow", name: "New workflow", description: "" },
  agents: {
    assistant: {
      name: "Assistant",
      inputSchema: { type: "object", properties: {} },
      outputSchema: { type: "string" },
      strategy: {
        kind: "model",
        modelRef: "default-model",
        prompt: "Respond to the supplied input.",
      },
      tools: [],
      resources: [],
    },
  },
  workflows: {
    main: {
      name: "Main",
      inputSchema: { type: "object", properties: {} },
      outputSchema: { type: "string" },
      nodes: {
        answer: { uses: "assistant", inputMapping: { ref: "workflow.input" } },
      },
      outputMapping: { ref: "nodes.answer.output" },
    },
  },
});
