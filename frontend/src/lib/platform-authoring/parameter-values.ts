import { parseJsonValue } from "./common/serialization";
import { parseSchemaJsonObject } from "./schema/codec";
import { createLaunchInputState } from "./schema/launch-input-state";
import { createValueEntryForSchema } from "./values/factories";
import { decodeValueEntry } from "./values/codec";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
export function isJsonObject(value: Json): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function finiteJson(value: Json): boolean {
  if (typeof value === "number") return Number.isFinite(value);
  if (value && typeof value === "object")
    return Object.values(value).every(finiteJson);
  return true;
}
export function parseParameters(text: string): Json {
  if (!text.trim()) throw new Error("Parameters JSON must be valid JSON.");
  const value = parseJsonValue<Json>("Parameters JSON", text, null);
  if (!finiteJson(value))
    throw new Error("Parameters must contain finite JSON numbers.");
  return value;
}
export function initialParameters(schema: JsonObject): Json {
  if (Object.prototype.hasOwnProperty.call(schema, "default"))
    return structuredClone(schema.default);
  const object = createLaunchInputState(schema);
  if (object.schemaSupported) return object.payload as Json;
  const parsed = parseSchemaJsonObject(schema);
  return parsed.builder
    ? (decodeValueEntry(createValueEntryForSchema(parsed.builder)) as Json)
    : null;
}
