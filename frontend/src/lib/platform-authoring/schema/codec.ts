import { CONSTRAINT_KEYS, TYPED_CONSTRAINTS, validateConstraintValue, validateSchemaConstraints } from "./constraints";
import type { UnknownRecord } from "@/lib/types/common";
import type { JsonPrimitive, JsonValue, SchemaIRNode, SchemaIRRef } from "./types";
import { createDefaultSchemaNode } from "./factories";
import {
  createSchemaValidationIssue,
  getUnsupportedSchemaKeywordMessage,
  joinSchemaPath,
  type SchemaValidationIssue,
} from "./validation";

export type SchemaCodecIssue = SchemaValidationIssue;

type SchemaCodecParseSuccess = {
  builder: ReturnType<typeof jsonSchemaToSchemaBuilder>;
  jsonSchema: UnknownRecord;
  issues: [];
};

type SchemaCodecParseFailure = {
  builder: null;
  jsonSchema: null;
  issues: SchemaCodecIssue[];
};

export type SchemaCodecParseResult = SchemaCodecParseSuccess | SchemaCodecParseFailure;

type PrimitiveKind = "boolean" | "integer" | "number" | "string";

type SchemaNodeContext = {
  issues: SchemaCodecIssue[];
  path: string;
  schema?: Record<string, unknown>;
};

const PRIMITIVE_TYPES = new Set(["string", "integer", "number", "boolean"]);
const REGISTRY_REF_RE = /^registry:\/\/(?<key>[a-z][a-z0-9_]{0,119})(?:@(?<version>[1-9][0-9]*))?$/;

function addIssue(issues: SchemaCodecIssue[], field: string, issue: string) {
  issues.push(createSchemaValidationIssue(field, issue));
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function hasOwnKey(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function isJsonValue(value: unknown): value is JsonValue {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return typeof value !== "number" || Number.isFinite(value);
  }

  if (Array.isArray(value)) {
    return value.every(isJsonValue);
  }

  if (isRecord(value)) {
    return Object.values(value).every(isJsonValue);
  }

  return false;
}

function toOptionalText(value: string | null | undefined) {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

function primitiveKindForValue(value: JsonPrimitive): PrimitiveKind {
  if (typeof value === "boolean") {
    return "boolean";
  }

  if (typeof value === "string") {
    return "string";
  }

  return Number.isInteger(value) ? "integer" : "number";
}

function primitiveValueToInput(value: JsonPrimitive): string {
  return typeof value === "string" ? value : String(value);
}

export function parsePrimitiveInput(value: string, kind: PrimitiveKind): JsonPrimitive {
  if (kind === "boolean") {
    return value.trim().toLowerCase() === "true";
  }

  if (kind === "integer") {
    return Number.parseInt(value.trim() || "0", 10);
  }

  if (kind === "number") {
    return Number.parseFloat(value.trim() || "0");
  }

  return value;
}

function parseLinePrimitive(value: string): JsonPrimitive {
  const trimmed = value.trim();

  if (trimmed === "true") {
    return true;
  }

  if (trimmed === "false") {
    return false;
  }

  if (/^-?\d+$/.test(trimmed)) {
    return Number.parseInt(trimmed, 10);
  }

  if (/^-?(?:\d+\.\d+|\d+\.\d*|\d*\.\d+)$/.test(trimmed)) {
    return Number.parseFloat(trimmed);
  }

  return trimmed;
}

export function formatPrimitiveList(values: JsonPrimitive[]) {
  return values.map(primitiveValueToInput).join("\n");
}

export function parsePrimitiveList(value: string): JsonPrimitive[] {
  return value
    .split(/\r?\n/)
    .map((entry) => entry.trim())
    .filter(Boolean)
    .map(parseLinePrimitive);
}

type ParsedDefaultValue =
  | { hasDefault: false }
  | { defaultValue: JsonValue; hasDefault: true };

function shouldPreserveEmptyMetadata(node: SchemaIRNode, context?: SchemaNodeContext): boolean {
  return context?.path === "jsonSchema" && (node.kind === "boolean" || node.kind === "integer" || node.kind === "number" || node.kind === "ref" || node.kind === "string");
}

function withMetadata<T extends SchemaIRNode>(
  node: T,
  title?: string,
  description?: string,
  parsedDefault: ParsedDefaultValue = { hasDefault: false },
  context?: SchemaNodeContext,
): T {
  const titleText = toOptionalText(title);
  const descriptionText = toOptionalText(description);
  const keepEmptyMetadata = shouldPreserveEmptyMetadata(node, context);
  const annotationVersion = context?.schema?.["x-signaldeck-schema"] as SchemaIRNode["annotationVersion"];
  const examples = context?.schema?.examples;
  const constraints = Object.fromEntries(Object.entries(context?.schema ?? {}).filter(([key]) => CONSTRAINT_KEYS.has(key)));
  const nextNode = {
    ...node,
    ...(annotationVersion ? { annotationVersion } : {}),
    ...(Array.isArray(examples) ? { examples } : {}),
    ...(Object.keys(constraints).length ? { constraints } : {}),
    ...(parsedDefault.hasDefault ? { defaultValue: parsedDefault.defaultValue } : {}),
    ...(descriptionText ? { description: descriptionText } : keepEmptyMetadata ? { description: null } : {}),
    ...(titleText ? { title: titleText } : keepEmptyMetadata ? { title: null } : {}),
  } as T;

  if (parsedDefault.hasDefault && context) {
    validateDefaultValue(nextNode, parsedDefault.defaultValue, joinSchemaPath(context.path as never, "default"), context.issues);
  }

  if (Array.isArray(examples) && context) {
    examples.forEach((value, index) => validateDefaultValue(nextNode, value as JsonValue, joinSchemaPath(context.path as never, `examples[${index}]`), context.issues));
  }
  return nextNode;
}

function withJsonMetadata(payload: UnknownRecord, node: SchemaIRNode) {
  const nextPayload = { ...payload, ...node.constraints };
  if (node.annotationVersion) nextPayload["x-signaldeck-schema"] = node.annotationVersion;
  if (hasOwnKey(node, "examples")) nextPayload.examples = node.examples;

  if (toOptionalText(node.title ?? undefined)) {
    nextPayload.title = node.title;
  }

  if (toOptionalText(node.description ?? undefined)) {
    nextPayload.description = node.description;
  }

  if (hasOwnKey(node, "defaultValue")) {
    nextPayload.default = node.defaultValue;
  }

  return nextPayload;
}

export function schemaBuilderToJsonSchema(node: SchemaIRNode): UnknownRecord {
  switch (node.kind) {
    case "string":
    case "integer":
    case "number":
    case "boolean": {
      return withJsonMetadata({ type: node.kind }, node);
    }
    case "enum": {
      const firstValue = node.values[0] ?? "value";
      return withJsonMetadata({ enum: node.values, type: primitiveKindForValue(firstValue) }, node);
    }
    case "literal": {
      return withJsonMetadata({ const: node.value, type: primitiveKindForValue(node.value) }, node);
    }
    case "array":
      return withJsonMetadata({ items: schemaBuilderToJsonSchema(node.items), type: "array" }, node);
    case "ref":
      return withJsonMetadata(
        { $ref: `registry://${node.schemaKey}${node.schemaVersion ? `@${node.schemaVersion}` : ""}` },
        node,
      );
    case "discriminated_union":
      return withJsonMetadata(
        {
          anyOf: node.variants.map((variant) => schemaBuilderToJsonSchema(variant)),
          discriminator: { propertyName: node.discriminator },
        },
        node,
      );
    case "object":
    default: {
      const fields = node.fields ?? [];
      return withJsonMetadata(
        {
          properties: Object.fromEntries(fields.map((field) => [field.name, schemaBuilderToJsonSchema(field.schema)])),
          required: fields.filter((field) => field.required !== false).map((field) => field.name),
          type: "object",
        },
        node,
      );
    }
  }
}

function readDefaultValue(schema: Record<string, unknown>, context: SchemaNodeContext): ParsedDefaultValue {
  if (!hasOwnKey(schema, "default")) {
    return { hasDefault: false };
  }

  if (!isJsonValue(schema.default)) {
    addIssue(context.issues, joinSchemaPath(context.path as never, "default"), "Default values must be valid JSON values");
    return { hasDefault: false };
  }

  return { defaultValue: schema.default, hasDefault: true };
}

function validateDefaultValue(node: SchemaIRNode, value: JsonValue, path: string, issues: SchemaCodecIssue[]) {
  validateConstraintValue(node, value, path, issues);
  if (value === null) {
    addIssue(issues, path, "Default values cannot be null");
    return;
  }

  switch (node.kind) {
    case "string":
      if (typeof value !== "string") {
        addIssue(issues, path, "Default value must be a string");
      }
      return;
    case "integer":
      if (typeof value !== "number" || !Number.isInteger(value)) {
        addIssue(issues, path, "Default value must be an integer");
      }
      return;
    case "number":
      if (typeof value !== "number") {
        addIssue(issues, path, "Default value must be a number");
      }
      return;
    case "boolean":
      if (typeof value !== "boolean") {
        addIssue(issues, path, "Default value must be a boolean");
      }
      return;
    case "enum":
      if (typeof value !== "boolean" && typeof value !== "number" && typeof value !== "string") {
        addIssue(issues, path, "Default value must be one of the enum values");
        return;
      }
      if (!node.values.some((entry) => entry === value)) {
        addIssue(issues, path, "Default value must be one of the enum values");
      }
      return;
    case "literal":
      if (node.value !== value) {
        addIssue(issues, path, "Default value must match the literal value");
      }
      return;
    case "array":
      if (!Array.isArray(value)) {
        addIssue(issues, path, "Default value must be an array");
        return;
      }
      value.forEach((item, index) => validateDefaultValue(node.items, item, joinSchemaPath(path as never, `[${index}]`), issues));
      return;
    case "object":
      validateObjectDefaultValue(node, value, path, issues);
      return;
    case "discriminated_union":
      if (!node.variants.some((variant) => collectDefaultIssues(variant, value, path).length === 0)) {
        addIssue(issues, path, "Default value must match one discriminated union variant");
      }
      return;
    case "ref":
      return;
  }
}

function collectDefaultIssues(node: SchemaIRNode, value: JsonValue, path: string): SchemaCodecIssue[] {
  const issues: SchemaCodecIssue[] = [];
  validateDefaultValue(node, value, path, issues);
  return issues;
}

export type SchemaDefaultValueTextResult =
  | { defaultValue: JsonValue; hasDefault: true; issues: SchemaCodecIssue[] }
  | { hasDefault: false; issues: SchemaCodecIssue[] };

export function validateSchemaDefaultValue(
  node: SchemaIRNode,
  value: JsonValue,
  path = "defaultValue",
): SchemaCodecIssue[] {
  return collectDefaultIssues(node, value, path);
}

export function parseSchemaDefaultValueText(
  node: SchemaIRNode,
  value: string,
  path = "defaultValue",
): SchemaDefaultValueTextResult {
  const trimmed = value.trim();
  if (!trimmed) {
    return { hasDefault: false, issues: [] };
  }

  try {
    const parsedValue = JSON.parse(trimmed) as unknown;
    if (!isJsonValue(parsedValue)) {
      return {
        hasDefault: false,
        issues: [createSchemaValidationIssue(path, "Default values must be valid JSON values")],
      };
    }

    return {
      defaultValue: parsedValue,
      hasDefault: true,
      issues: validateSchemaDefaultValue(node, parsedValue, path),
    };
  } catch {
    return {
      hasDefault: false,
      issues: [createSchemaValidationIssue(path, "Default value must be valid JSON.")],
    };
  }
}

function validateObjectDefaultValue(node: Extract<SchemaIRNode, { kind: "object" }>, value: JsonValue, path: string, issues: SchemaCodecIssue[]) {
  if (!isRecord(value)) {
    addIssue(issues, path, "Default value must be an object");
    return;
  }

  const fields = node.fields ?? [];
  const fieldMap = new Map(fields.map((field) => [field.name, field]));

  for (const field of fields) {
    if (field.required !== false && !hasOwnKey(value, field.name)) {
      addIssue(issues, joinSchemaPath(path as never, field.name), "Required field is missing from the default value");
    }
  }

  for (const [key, entryValue] of Object.entries(value)) {
    const field = fieldMap.get(key);
    if (!field) {
      addIssue(issues, joinSchemaPath(path as never, key), "Default object contains an unsupported field");
      continue;
    }

    validateDefaultValue(field.schema, entryValue, joinSchemaPath(path as never, key), issues);
  }
}

export function parseSchemaJsonObject(jsonSchema: unknown): SchemaCodecParseResult {
  const issues: SchemaCodecIssue[] = [];
  const builder = jsonSchemaToSchemaBuilder(jsonSchema, { issues, path: "jsonSchema" });
  if (issues.length > 0) {
    return { builder: null, jsonSchema: null, issues };
  }

  return { builder, jsonSchema: jsonSchema as UnknownRecord, issues: [] };
}

export function parseSchemaJsonText(value: string): SchemaCodecParseResult {
  const trimmed = value.trim();
  if (!trimmed) {
    return {
      builder: null,
      jsonSchema: null,
      issues: [createSchemaValidationIssue("jsonSchema", "A schema definition is required")],
    };
  }

  try {
    return parseSchemaJsonObject(JSON.parse(trimmed) as unknown);
  } catch {
    return {
      builder: null,
      jsonSchema: null,
      issues: [createSchemaValidationIssue("jsonSchema", "JSON Schema must be valid JSON.")],
    };
  }
}

function jsonSchemaToSchemaBuilder(schema: unknown, context: SchemaNodeContext): SchemaIRNode {
  if (!isRecord(schema)) {
    addIssue(context.issues, context.path, "Schema nodes must be objects");
    return createDefaultSchemaNode("string");
  }

  context = { ...context, schema };
  const version = schema["x-signaldeck-schema"];
  if (version !== undefined && version !== "signaldeck.schema/1" && version !== "signaldeck.schema/2") addIssue(context.issues, `${context.path}.x-signaldeck-schema`, "Unsupported schema version");
  for (const key of ["default", "examples"]) {
    if (hasOwnKey(schema, key) && version !== "signaldeck.schema/2") addIssue(context.issues, `${context.path}.${key}`, "Annotations require x-signaldeck-schema: signaldeck.schema/2 on this node");
  }
  if (hasOwnKey(schema, "examples") && (!Array.isArray(schema.examples) || !isJsonValue(schema.examples))) addIssue(context.issues, `${context.path}.examples`, "Examples must be an array of JSON values");
  const title = readOptionalString(schema.title, joinSchemaPath(context.path as never, "title"), context.issues);
  const description = readOptionalString(
    schema.description,
    joinSchemaPath(context.path as never, "description"),
    context.issues,
  );
  const parsedDefault = readDefaultValue(schema, context);

  for (const key of ["allOf", "if", "then", "else", "not", "oneOf"] as const) {
    if (key in schema) {
      addIssue(context.issues, joinSchemaPath(context.path as never, key), getUnsupportedSchemaKeywordMessage(key));
    }
  }

  if ("$ref" in schema) {
    validateAllowedKeys(schema, new Set(["$ref", "default", "title", "description"]), context);
    return withMetadata(parseRefBuilder(schema.$ref, context), title, description, parsedDefault, context);
  }

  if ("anyOf" in schema) {
    validateAllowedKeys(schema, new Set(["anyOf", "default", "discriminator", "title", "description"]), context);
    const anyOf = schema.anyOf;
    if (!Array.isArray(anyOf) || anyOf.length < 2) {
      addIssue(
        context.issues,
        joinSchemaPath(context.path as never, "anyOf"),
        "Discriminated unions must include at least two variants",
      );
      return withMetadata(createDefaultSchemaNode("discriminated_union"), title, description, parsedDefault, context);
    }

    if (!("discriminator" in schema)) {
      addIssue(
        context.issues,
        joinSchemaPath(context.path as never, "anyOf"),
        "Undiscriminated unions are not supported",
      );
    }

    const discriminator = parseDiscriminator(
      schema.discriminator,
      joinSchemaPath(context.path as never, "discriminator"),
      context.issues,
    );

    return withMetadata(
      {
        kind: "discriminated_union",
        discriminator,
        variants: anyOf.map((variant, index) =>
          jsonSchemaToSchemaBuilder(variant, {
            issues: context.issues,
            path: joinSchemaPath(context.path as never, `anyOf[${index}]`),
          }),
        ),
      },
      title,
      description,
      parsedDefault,
      context,
    );
  }

  if ("const" in schema) {
    validateAllowedKeys(schema, new Set(["const", "default", "type", "title", "description"]), context);
    const literal = parseJsonPrimitive(schema.const, joinSchemaPath(context.path as never, "const"), context.issues);
    validateDeclaredPrimitiveType(schema.type, literal !== null ? primitiveKindForValue(literal) : undefined, context);
    return withMetadata({ kind: "literal", value: literal ?? "value" }, title, description, parsedDefault, context);
  }

  if ("enum" in schema) {
    validateAllowedKeys(schema, new Set(["default", "enum", "type", "title", "description"]), context);
    if (!Array.isArray(schema.enum) || schema.enum.length === 0) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "enum"), "Enum values must be a non-empty array");
      return withMetadata(createDefaultSchemaNode("enum"), title, description, parsedDefault, context);
    }

    const values = schema.enum
      .map((entry, index) => parseJsonPrimitive(entry, joinSchemaPath(context.path as never, `enum[${index}]`), context.issues))
      .filter((entry): entry is JsonPrimitive => entry !== null);

    if (values.length > 0 && new Set(values.map((entry) => primitiveKindForValue(entry))).size > 1) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "enum"), "Enum values must all use the same primitive type");
    }

    validateDeclaredPrimitiveType(schema.type, values[0] !== undefined ? primitiveKindForValue(values[0]) : undefined, context);
    return withMetadata({ kind: "enum", values: values.length > 0 ? values : ["value"] }, title, description, parsedDefault, context);
  }

  if (typeof schema.type !== "string") {
    addIssue(context.issues, joinSchemaPath(context.path as never, "type"), "Schema type is required");
    return withMetadata(createDefaultSchemaNode("string"), title, description, parsedDefault, context);
  }

  if (PRIMITIVE_TYPES.has(schema.type)) {
    validateAllowedKeys(schema, new Set(["default", "type", "title", "description"]), context);
    return withMetadata({ kind: schema.type as PrimitiveKind }, title, description, parsedDefault, context);
  }

  if (schema.type === "array") {
    validateAllowedKeys(schema, new Set(["default", "type", "items", "title", "description"]), context);
    if (Array.isArray(schema.items)) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "items"), "Tuple arrays are not supported");
      return withMetadata(createDefaultSchemaNode("array"), title, description, parsedDefault, context);
    }

    if (schema.items === undefined) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "items"), "Array items are required");
      return withMetadata(createDefaultSchemaNode("array"), title, description, parsedDefault, context);
    }

    return withMetadata(
      {
        kind: "array",
        items: jsonSchemaToSchemaBuilder(schema.items, { issues: context.issues, path: joinSchemaPath(context.path as never, "items") }),
      },
      title,
      description,
      parsedDefault,
      context,
    );
  }

  if (schema.type === "object") {
    validateAllowedKeys(
      schema,
      new Set(["default", "type", "properties", "required", "title", "description"]),
      context,
    );

    const properties = schema.properties ?? {};
    if (!isRecord(properties)) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "properties"), "Object properties must be an object");
      return withMetadata(createDefaultSchemaNode("object"), title, description, parsedDefault, context);
    }

    const rawRequired = Array.isArray(schema.required) ? schema.required : [];
    if (schema.required !== undefined && !Array.isArray(schema.required)) {
      addIssue(context.issues, joinSchemaPath(context.path as never, "required"), "Required fields must be an array");
    }

    const requiredSet = new Set<string>();
    rawRequired.forEach((entry, index) => {
      if (typeof entry !== "string" || !entry.trim()) {
        addIssue(
          context.issues,
          joinSchemaPath(context.path as never, `required[${index}]`),
          "Required field names must be non-empty strings",
        );
        return;
      }

      requiredSet.add(entry);
    });

    const fields = Object.entries(properties).map(([name, childSchema]) => ({
      name,
      required: requiredSet.has(name),
      schema: jsonSchemaToSchemaBuilder(childSchema, {
        issues: context.issues,
        path: joinSchemaPath(context.path as never, `properties.${name}`),
      }),
    }));

    for (const requiredField of [...requiredSet].filter((name) => !(name in properties))) {
      addIssue(
        context.issues,
        joinSchemaPath(context.path as never, "required"),
        `Required field ${JSON.stringify(requiredField)} is not defined in properties`,
      );
    }

    return withMetadata(
      {
        kind: "object",
        fields,
      },
      title,
      description,
      parsedDefault,
      context,
    );
  }

  addIssue(context.issues, joinSchemaPath(context.path as never, "type"), `Schema type ${JSON.stringify(schema.type)} is not supported`);
  return withMetadata(createDefaultSchemaNode("string"), title, description, parsedDefault, context);
}

function validateAllowedKeys(schema: Record<string, unknown>, allowedKeys: Set<string>, context: SchemaNodeContext) {
  for (const key of ["x-signaldeck-schema", "examples", "$schema", ...(TYPED_CONSTRAINTS[String(schema.type)] ?? [])]) allowedKeys.add(key);
  validateSchemaConstraints(schema, context.path, context.issues);
  for (const key of Object.keys(schema).sort()) {
    if (allowedKeys.has(key)) {
      continue;
    }

    addIssue(context.issues, joinSchemaPath(context.path as never, key), getUnsupportedSchemaKeywordMessage(key));
  }
}

function readOptionalString(value: unknown, path: string, issues: SchemaCodecIssue[]) {
  if (value === undefined || value === null) {
    return undefined;
  }

  if (typeof value !== "string") {
    addIssue(issues, path, `${path.endsWith("title") ? "title" : "description"} must be a string`);
    return undefined;
  }

  const trimmed = value.trim();
  return trimmed ? trimmed : undefined;
}

function parseJsonPrimitive(value: unknown, path: string, issues: SchemaCodecIssue[]) {
  if (typeof value === "boolean" || typeof value === "string" || typeof value === "number") {
    return value as JsonPrimitive;
  }

  addIssue(issues, path, "Values must be JSON primitives");
  return null;
}

function validateDeclaredPrimitiveType(
  declaredType: unknown,
  expectedType: PrimitiveKind | undefined,
  context: SchemaNodeContext,
) {
  if (declaredType === undefined || expectedType === undefined) {
    return;
  }

  if (typeof declaredType !== "string") {
    addIssue(context.issues, joinSchemaPath(context.path as never, "type"), "Schema type must be a string");
    return;
  }

  if (declaredType !== expectedType) {
    addIssue(
      context.issues,
      joinSchemaPath(context.path as never, "type"),
      `Declared type ${JSON.stringify(declaredType)} does not match the literal or enum values`,
    );
  }
}

function parseDiscriminator(value: unknown, path: string, issues: SchemaCodecIssue[]) {
  if (typeof value === "string" && value.trim()) {
    return value.trim();
  }

  if (isRecord(value) && typeof value.propertyName === "string" && value.propertyName.trim()) {
    return value.propertyName.trim();
  }

  addIssue(issues, path, "Discriminator must define propertyName");
  return "kind";
}

function parseRefBuilder(value: unknown, context: SchemaNodeContext): SchemaIRRef {
  if (typeof value !== "string") {
    addIssue(context.issues, joinSchemaPath(context.path as never, "$ref"), "Registry refs must be strings");
    return { kind: "ref", schemaKey: "shared_schema" } as const;
  }

  const match = REGISTRY_REF_RE.exec(value.trim());
  if (!match?.groups?.key) {
    addIssue(
      context.issues,
      joinSchemaPath(context.path as never, "$ref"),
      "Registry refs must use registry://<key> or registry://<key>@<version>",
    );
    return { kind: "ref", schemaKey: "shared_schema" } as const;
  }

  return {
    kind: "ref",
    schemaKey: match.groups.key,
    schemaVersion: match.groups.version ? Number.parseInt(match.groups.version, 10) : undefined,
  } as const;
}
