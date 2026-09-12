import { parseJsonValue } from "./common/serialization";
import { newInputValue } from "./schema/input-values";
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
  return newInputValue(schema);
}
