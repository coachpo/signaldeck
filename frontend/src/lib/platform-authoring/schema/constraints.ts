import type { JsonValue, SchemaIRNode } from "./types";
import { createSchemaValidationIssue, type SchemaValidationIssue } from "./validation";

function addIssue(issues: SchemaValidationIssue[], field: string, issue: string) {
  issues.push(createSchemaValidationIssue(field, issue));
}
function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}
function hasOwnKey(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

export const TYPED_CONSTRAINTS: Record<string, string[]> = {
  string: ["minLength", "maxLength"],
  integer: ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"],
  number: ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"],
  array: ["minItems", "maxItems", "uniqueItems"],
  object: ["minProperties", "maxProperties", "unevaluatedProperties"],
};
export const CONSTRAINT_KEYS = new Set(["$schema", ...Object.values(TYPED_CONSTRAINTS).flat()]);

export function validateSchemaConstraints(schema: Record<string, unknown>, path: string, issues: SchemaValidationIssue[]) {
  for (const key of TYPED_CONSTRAINTS[String(schema.type)] ?? []) {
    const value = schema[key];
    if (value === undefined) continue;
    const booleanKey = key === "uniqueItems" || key === "unevaluatedProperties";
    const countKey = ["minLength", "maxLength", "minItems", "maxItems", "minProperties", "maxProperties"].includes(key);
    if (booleanKey ? typeof value !== "boolean" : typeof value !== "number" || !Number.isFinite(value) || (countKey && (!Number.isInteger(value) || value < 0)) || (key === "multipleOf" && value <= 0)) addIssue(issues, `${path}.${key}`, "Invalid schema constraint");
  }
  if (schema.$schema !== undefined && schema.$schema !== "https://json-schema.org/draft/2020-12/schema") addIssue(issues, `${path}.$schema`, "Only JSON Schema 2020-12 is supported");
  if (schema.unevaluatedProperties !== undefined && schema.unevaluatedProperties !== false) addIssue(issues, `${path}.unevaluatedProperties`, "Objects are closed");
}

export function validateConstraintValue(node: SchemaIRNode, value: JsonValue, path: string, issues: SchemaValidationIssue[]) {
  const constraints = node.constraints ?? {};
  const checkBound = (key: string, actual: number, predicate: (actual: number, limit: number) => boolean) => {
    const limit = constraints[key];
    if (typeof limit === "number" && !predicate(actual, limit)) addIssue(issues, path, `Value violates ${key}: ${limit}`);
  };
  if (typeof value === "string") {
    checkBound("minLength", [...value].length, (a, b) => a >= b);
    checkBound("maxLength", [...value].length, (a, b) => a <= b);
  }
  if (typeof value === "number") {
    checkBound("minimum", value, (a, b) => a >= b);
    checkBound("maximum", value, (a, b) => a <= b);
    checkBound("exclusiveMinimum", value, (a, b) => a > b);
    checkBound("exclusiveMaximum", value, (a, b) => a < b);
    checkBound("multipleOf", value, (a, b) => Math.abs(a / b - Math.round(a / b)) < 1e-10);
  }
  if (Array.isArray(value)) {
    checkBound("minItems", value.length, (a, b) => a >= b);
    checkBound("maxItems", value.length, (a, b) => a <= b);
    if (constraints.uniqueItems === true && value.some((entry, index) => value.slice(0, index).some((prior) => jsonValuesEqual(prior, entry)))) addIssue(issues, path, "Array values must be unique");
  } else if (isRecord(value)) {
    checkBound("minProperties", Object.keys(value).length, (a, b) => a >= b);
    checkBound("maxProperties", Object.keys(value).length, (a, b) => a <= b);
  }
}

function jsonValuesEqual(left: JsonValue, right: JsonValue): boolean {
  if (left === right) return true;
  if (Array.isArray(left) && Array.isArray(right)) return left.length === right.length && left.every((entry, index) => jsonValuesEqual(entry, right[index]));
  if (isRecord(left) && isRecord(right)) return Object.keys(left).length === Object.keys(right).length && Object.keys(left).every((key) => hasOwnKey(right, key) && jsonValuesEqual(left[key] as JsonValue, right[key] as JsonValue));
  return false;
}
