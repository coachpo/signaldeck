import { parseJsonValue, stringifyJson } from "../common/serialization";
import { parseSchemaJsonObject, type SchemaCodecIssue } from "./codec";
import type {
  JsonPrimitive,
  SchemaIRField,
  SchemaIRNode,
  SchemaIRObject,
} from "./types";
import {
  createArrayValueEntry,
  createBooleanValueEntry,
  createIntegerValueEntry,
  createNullValueEntry,
  createNumberValueEntry,
  createObjectValueEntry,
  createPrimitiveValueEntry,
  createStringValueEntry,
  createValueEntryArrayItem,
  createValueEntryForSchema,
  createValueEntryObjectField,
  rebaseValueEntryPaths,
} from "../values/factories";
import { decodeValueEntry, encodeValueEntry } from "../values/codec";
import type {
  ValueEntry,
  ValueEntryObject,
  ValueEntryPath,
} from "../values/types";
import type { UnknownRecord } from "@/lib/types/common";

export type LaunchInputState = {
  draft: ValueEntryObject | null;
  formattedJson: string;
  issues: SchemaCodecIssue[];
  nullablePathKeys: readonly string[];
  payload: UnknownRecord;
  reason: string | null;
  schema: SchemaIRObject | null;
  schemaSupported: boolean;
};

export type LaunchInputApplyIssue = {
  field: string;
  issue: string;
};

type NullableSchema = {
  nullablePathKeys: string[];
  schema: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function isUnknownRecord(value: unknown): value is UnknownRecord {
  return isRecord(value);
}

function pathKey(pathTokens: readonly string[]): string {
  return pathTokens.join("\u0000");
}

function extendPath(pathTokens: ValueEntryPath, token: string): ValueEntryPath {
  return [...pathTokens, token];
}

function runtimeInputField(pathTokens: readonly string[]): string {
  return ["parameters", ...pathTokens].join(".");
}

function hasOwnKey(value: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(value, key);
}

function nullableType(value: unknown): string | null {
  if (!Array.isArray(value) || value.length !== 2 || !value.includes("null")) {
    return null;
  }
  const declared = value.find((entry) => entry !== "null");
  return typeof declared === "string" ? declared : null;
}

function normalizeNullableSchemaNode(
  value: unknown,
  pathTokens: ValueEntryPath,
): NullableSchema {
  if (!isRecord(value)) {
    return { nullablePathKeys: [], schema: value };
  }

  const nextSchema: Record<string, unknown> = { ...value };
  const nullablePathKeys: string[] = [];
  const declaredNullableType = nullableType(value.type);

  if (declaredNullableType) {
    nextSchema.type = declaredNullableType;
    nullablePathKeys.push(pathKey(pathTokens));
    if (Array.isArray(nextSchema.enum)) {
      nextSchema.enum = nextSchema.enum.filter((entry) => entry !== null);
    }
  }

  if (isRecord(nextSchema.properties)) {
    nextSchema.properties = Object.fromEntries(
      Object.entries(nextSchema.properties).map(([key, childSchema]) => {
        const normalized = normalizeNullableSchemaNode(
          childSchema,
          extendPath(pathTokens, key),
        );
        nullablePathKeys.push(...normalized.nullablePathKeys);
        return [key, normalized.schema];
      }),
    );
  }

  if (nextSchema.items !== undefined && !Array.isArray(nextSchema.items)) {
    const normalized = normalizeNullableSchemaNode(
      nextSchema.items,
      extendPath(pathTokens, "0"),
    );
    nextSchema.items = normalized.schema;
    nullablePathKeys.push(...normalized.nullablePathKeys);
  }

  return { nullablePathKeys, schema: nextSchema };
}

function nullablePathSet(
  state: Pick<LaunchInputState, "nullablePathKeys">,
): ReadonlySet<string> {
  return new Set(state.nullablePathKeys);
}

function isNullableValuePath(
  nullablePaths: ReadonlySet<string>,
  pathTokens: ValueEntryPath,
): boolean {
  const exactPathKey = pathKey(pathTokens);
  if (nullablePaths.has(exactPathKey)) {
    return true;
  }

  const normalizedArrayItemPathKey = pathKey(
    pathTokens.map((token) => (/^\d+$/.test(token) ? "0" : token)),
  );
  return nullablePaths.has(normalizedArrayItemPathKey);
}

function createScalarValueEntryFromPayload(
  schema: SchemaIRNode,
  value: unknown,
  pathTokens: ValueEntryPath,
): ValueEntry | null {
  switch (schema.kind) {
    case "string":
      return typeof value === "string"
        ? createStringValueEntry(value, pathTokens)
        : null;
    case "integer":
      return typeof value === "number" && Number.isInteger(value)
        ? createIntegerValueEntry(value, pathTokens)
        : null;
    case "number":
      return typeof value === "number"
        ? createNumberValueEntry(value, pathTokens)
        : null;
    case "boolean":
      return typeof value === "boolean"
        ? createBooleanValueEntry(value, pathTokens)
        : null;
    case "enum":
      if (value === null || Array.isArray(value) || isRecord(value)) {
        return null;
      }
      return schema.values.some((option) => option === value)
        ? createPrimitiveValueEntry(value as JsonPrimitive, pathTokens)
        : null;
    case "literal":
      return encodeValueEntry(value, pathTokens);
    default:
      return null;
  }
}

function createDraftFromPayloadNode(
  schema: SchemaIRNode,
  value: unknown,
  pathTokens: ValueEntryPath,
  nullablePaths: ReadonlySet<string>,
): ValueEntry {
  if (value === null && isNullableValuePath(nullablePaths, pathTokens)) {
    return createNullValueEntry(pathTokens);
  }

  const scalarEntry = createScalarValueEntryFromPayload(
    schema,
    value,
    pathTokens,
  );
  if (scalarEntry) {
    return scalarEntry;
  }

  if (schema.kind === "array" && Array.isArray(value)) {
    return createArrayValueEntry(
      value.map((item, index) => {
        const itemPath = extendPath(pathTokens, String(index));
        return createValueEntryArrayItem(
          index,
          createDraftFromPayloadNode(
            schema.items,
            item,
            itemPath,
            nullablePaths,
          ),
          itemPath,
        );
      }),
      pathTokens,
    );
  }

  if (schema.kind === "object" && isRecord(value)) {
    return createObjectValueEntry(
      createObjectFieldsFromPayload(
        schema.fields ?? [],
        value,
        pathTokens,
        nullablePaths,
      ),
      pathTokens,
    );
  }

  return encodeValueEntry(value, pathTokens);
}

function createObjectFieldsFromPayload(
  fields: readonly SchemaIRField[],
  value: Record<string, unknown>,
  pathTokens: ValueEntryPath,
  nullablePaths: ReadonlySet<string>,
) {
  const sortedFields = [...fields].sort((left, right) =>
    left.name.localeCompare(right.name),
  );
  const knownFieldNames = new Set(sortedFields.map((field) => field.name));
  const knownFields = sortedFields
    .filter((field) => hasOwnKey(value, field.name))
    .map((field) => {
      const fieldPath = extendPath(pathTokens, field.name);
      const fieldValue = createDraftFromPayloadNode(
        field.schema, value[field.name], fieldPath, nullablePaths,
      );
      return createValueEntryObjectField(field.name, fieldValue, fieldPath);
    });
  const extraFields = Object.entries(value)
    .filter(([key]) => !knownFieldNames.has(key))
    .map(([key, entryValue]) => {
      const fieldPath = extendPath(pathTokens, key);
      return createValueEntryObjectField(
        key,
        encodeValueEntry(entryValue, fieldPath),
        fieldPath,
      );
    });

  return [...knownFields, ...extraFields];
}

function expectedSchemaValueLabel(schema: SchemaIRNode): string {
  switch (schema.kind) {
    case "enum":
      return "one of the declared enum values";
    case "literal":
      return stringifyJson(schema.value);
    case "integer":
      return "an integer";
    case "discriminated_union":
      return "a matching discriminated union object";
    case "ref":
      return "a JSON value";
    default:
      return `a ${schema.kind}`;
  }
}

function typeIssue(
  schema: SchemaIRNode,
  pathTokens: ValueEntryPath,
): LaunchInputApplyIssue {
  return {
    field: runtimeInputField(pathTokens),
    issue: `Expected ${expectedSchemaValueLabel(schema)}.`,
  };
}

function selectedDiscriminatedUnionVariant(
  schema: Extract<SchemaIRNode, { kind: "discriminated_union" }>,
  value: unknown,
): SchemaIRNode {
  if (isRecord(value)) {
    const selectedVariant = schema.variants.find((variant) => {
      if (variant.kind !== "object") {
        return false;
      }
      const discriminatorField = (variant.fields ?? []).find(
        (field) => field.name === schema.discriminator,
      );
      return (
        discriminatorField?.schema.kind === "literal" &&
        value[schema.discriminator] === discriminatorField.schema.value
      );
    });
    if (selectedVariant) {
      return selectedVariant;
    }
  }
  return schema.variants[0] ?? { fields: [], kind: "object" };
}

function validatePayloadNodeForDraft(
  schema: SchemaIRNode,
  value: unknown,
  pathTokens: ValueEntryPath,
  nullablePaths: ReadonlySet<string>,
): LaunchInputApplyIssue[] {
  if (value === null) {
    return isNullableValuePath(nullablePaths, pathTokens)
      ? []
      : [
          {
            field: runtimeInputField(pathTokens),
            issue: "Null is only allowed for nullable runtime input fields.",
          },
        ];
  }

  switch (schema.kind) {
    case "string":
      return typeof value === "string" ? [] : [typeIssue(schema, pathTokens)];
    case "integer":
      return typeof value === "number" && Number.isInteger(value)
        ? []
        : [typeIssue(schema, pathTokens)];
    case "number":
      return typeof value === "number" ? [] : [typeIssue(schema, pathTokens)];
    case "boolean":
      return typeof value === "boolean" ? [] : [typeIssue(schema, pathTokens)];
    case "enum":
      return value !== null &&
        !Array.isArray(value) &&
        !isRecord(value) &&
        schema.values.some((option) => option === value)
        ? []
        : [typeIssue(schema, pathTokens)];
    case "literal":
      return value === schema.value ? [] : [typeIssue(schema, pathTokens)];
    case "array":
      return Array.isArray(value)
        ? value.flatMap((item, index) =>
            validatePayloadNodeForDraft(
              schema.items,
              item,
              extendPath(pathTokens, String(index)),
              nullablePaths,
            ),
          )
        : [typeIssue(schema, pathTokens)];
    case "object": {
      if (!isRecord(value)) {
        return [typeIssue(schema, pathTokens)];
      }
      const fields = [...(schema.fields ?? [])].sort((left, right) =>
        left.name.localeCompare(right.name),
      );
      const knownFieldNames = new Set(fields.map((field) => field.name));
      const extraIssues = Object.keys(value)
        .filter((key) => !knownFieldNames.has(key))
        .sort((left, right) => left.localeCompare(right))
        .map((key) => ({
          field: runtimeInputField(extendPath(pathTokens, key)),
          issue: "Extra inputs are not permitted.",
        }));
      const fieldIssues = fields.flatMap((field) => {
        const fieldPath = extendPath(pathTokens, field.name);
        if (hasOwnKey(value, field.name)) {
          return validatePayloadNodeForDraft(
            field.schema,
            value[field.name],
            fieldPath,
            nullablePaths,
          );
        }
        return field.required !== false
          ? [
              {
                field: runtimeInputField(fieldPath),
                issue: "Field is required.",
              },
            ]
          : [];
      });
      return [...extraIssues, ...fieldIssues];
    }
    case "discriminated_union":
      return validatePayloadNodeForDraft(
        selectedDiscriminatedUnionVariant(schema, value),
        value,
        pathTokens,
        nullablePaths,
      );
    case "ref":
      return [];
  }
}

function validateLaunchPayloadForDraft(
  state: Pick<LaunchInputState, "nullablePathKeys" | "schema">,
  payload: UnknownRecord,
): LaunchInputApplyIssue[] {
  if (!state.schema) {
    return [];
  }
  return validatePayloadNodeForDraft(
    state.schema,
    payload,
    [],
    nullablePathSet(state),
  );
}

export function validateLaunchValueForSchema(
  inputSchema: unknown,
  payload: unknown,
): LaunchInputApplyIssue[] {
  const normalized = normalizeNullableSchemaNode(inputSchema, []);
  const parsed = parseSchemaJsonObject(normalized.schema);
  if (!parsed.builder) return [];
  return validatePayloadNodeForDraft(
    parsed.builder,
    payload,
    [],
    new Set(normalized.nullablePathKeys),
  );
}

export function createLaunchDraftFromValidatedPayload(
  state: Pick<LaunchInputState, "nullablePathKeys" | "schema">,
  payload: UnknownRecord,
): { draft: ValueEntryObject | null; issues: LaunchInputApplyIssue[] } {
  const issues = validateLaunchPayloadForDraft(state, payload);
  if (issues.length > 0) {
    return { draft: null, issues };
  }
  return { draft: createLaunchDraftFromPayload(state, payload), issues };
}

export function createLaunchDraftFromPayload(
  state: Pick<LaunchInputState, "nullablePathKeys" | "schema">,
  payload: UnknownRecord,
): ValueEntryObject | null {
  if (!state.schema) {
    return null;
  }
  const nullablePaths = nullablePathSet(state);
  const draft = createDraftFromPayloadNode(
    state.schema,
    payload,
    [],
    nullablePaths,
  );
  return draft.kind === "object" ? draft : createObjectValueEntry([], []);
}

function decodeValueEntryForPayload(value: ValueEntry): unknown {
  return decodeValueEntry(value);
}

export function createLaunchPayloadFromDraft(
  value: ValueEntryObject,
): UnknownRecord {
  const decoded = decodeValueEntryForPayload(value);
  return isUnknownRecord(decoded) ? decoded : {};
}

function formatLaunchPayloadJson(payload: UnknownRecord): string {
  return stringifyJson(payload);
}

export function formatLaunchDraftJson(value: ValueEntryObject): string {
  return formatLaunchPayloadJson(createLaunchPayloadFromDraft(value));
}

export function parseLaunchPayloadJson(parametersText: string): UnknownRecord {
  const parsed = parseJsonValue<unknown>(
    "Runtime inputs JSON",
    parametersText,
    {},
  );
  if (!isUnknownRecord(parsed)) {
    throw new Error("Runtime inputs JSON must be a valid object.");
  }
  return parsed;
}

function valueEntryMatches(value: ValueEntry, expected: ValueEntry): boolean {
  return JSON.stringify(value) === JSON.stringify(expected);
}

function preserveNullableNullField(
  field: ReturnType<typeof createValueEntryObjectField>,
  previousField: ReturnType<typeof createValueEntryObjectField> | undefined,
  schema: SchemaIRNode,
  nullablePaths: ReadonlySet<string>,
) {
  if (
    previousField?.value.kind === "null" &&
    isNullableValuePath(nullablePaths, field.pathTokens) &&
    valueEntryMatches(
      field.value,
      createValueEntryForSchema(schema, field.pathTokens),
    )
  ) {
    return createValueEntryObjectField(
      field.key,
      previousField.value,
      field.pathTokens,
    );
  }
  return field;
}

function preserveDraftNode(
  schema: SchemaIRNode,
  previous: ValueEntry | undefined,
  next: ValueEntry,
  nullablePaths: ReadonlySet<string>,
): ValueEntry {
  if (
    schema.kind !== "object" ||
    previous?.kind !== "object" ||
    next.kind !== "object"
  ) {
    return next;
  }

  const schemaFields = new Map(
    (schema.fields ?? []).map((field) => [field.name, field]),
  );
  const previousFields = new Map(
    previous.fields.map((field) => [field.key, field]),
  );
  const nextFieldKeys = new Set(next.fields.map((field) => field.key));
  const reconciledFields = next.fields.map((field) => {
    const schemaField = schemaFields.get(field.key);
    const previousField = previousFields.get(field.key);
    if (!schemaField) {
      return field;
    }
    const preservedChild = preserveDraftNode(
      schemaField.schema,
      previousField?.value,
      field.value,
      nullablePaths,
    );
    return preserveNullableNullField(
      createValueEntryObjectField(field.key, preservedChild, field.pathTokens),
      previousField,
      schemaField.schema,
      nullablePaths,
    );
  });
  const extraFields = previous.fields
    .filter(
      (field) => !schemaFields.has(field.key) && !nextFieldKeys.has(field.key),
    )
    .map((field) =>
      createValueEntryObjectField(
        field.key,
        rebaseValueEntryPaths(field.value, field.pathTokens),
        field.pathTokens,
      ),
    );

  return createObjectValueEntry(
    [...reconciledFields, ...extraFields],
    next.pathTokens,
  );
}

export function reconcileLaunchDraftChange(
  state: Pick<LaunchInputState, "nullablePathKeys" | "schema">,
  previous: ValueEntryObject | null,
  next: ValueEntry,
): ValueEntryObject {
  const schema = state.schema;
  if (!schema) {
    return next.kind === "object" ? next : createObjectValueEntry([], []);
  }
  const reconciled = preserveDraftNode(
    schema,
    previous ?? undefined,
    next,
    nullablePathSet(state),
  );
  return reconciled.kind === "object"
    ? reconciled
    : createObjectValueEntry([], []);
}

export function createLaunchInputState(inputSchema: unknown): LaunchInputState {
  const normalized = normalizeNullableSchemaNode(inputSchema, []);
  const parsed = parseSchemaJsonObject(normalized.schema);
  if (!parsed.builder) {
    const payload = {};
    return {
      draft: null,
      formattedJson: stringifyJson(payload),
      issues: parsed.issues,
      nullablePathKeys: normalized.nullablePathKeys,
      payload,
      reason:
        "The workflow input schema could not be converted into the supported package schema template, so the raw JSON editor starts from an empty object.",
      schema: null,
      schemaSupported: false,
    };
  }

  if (parsed.builder.kind !== "object") {
    const payload = {};
    return {
      draft: null,
      formattedJson: stringifyJson(payload),
      issues: [],
      nullablePathKeys: normalized.nullablePathKeys,
      payload,
      reason:
        "Workflow launch parameters must use an object input schema, so the raw JSON editor starts from an empty object.",
      schema: null,
      schemaSupported: false,
    };
  }

  const schema = parsed.builder;
  const objectDraft =
    createLaunchDraftFromPayload(
      { nullablePathKeys: normalized.nullablePathKeys, schema },
      decodeValueEntry(createValueEntryForSchema(schema)) as UnknownRecord,
    ) ?? createObjectValueEntry([], []);
  const payload = createLaunchPayloadFromDraft(objectDraft);
  return {
    draft: objectDraft,
    formattedJson: stringifyJson(payload),
    issues: [],
    nullablePathKeys: normalized.nullablePathKeys,
    payload,
    reason: null,
    schema,
    schemaSupported: true,
  };
}
