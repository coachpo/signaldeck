import type { JsonPrimitive, JsonValue, SchemaIRDiscriminatedUnion, SchemaIRNode } from "../schema/types";
import type {
  ValueEntry,
  ValueEntryArray,
  ValueEntryArrayItem,
  ValueEntryBoolean,
  ValueEntryInteger,
  ValueEntryKind,
  ValueEntryNull,
  ValueEntryObject,
  ValueEntryObjectField,
  ValueEntryNumber,
  ValueEntryPath,
  ValueEntryScalar,
  ValueEntryString,
} from "./types";

const DEFAULT_VALUE_ENTRY_PATH: ValueEntryPath = [];

function createValueEntryPath(pathTokens: readonly string[] = []): ValueEntryPath {
  return [...pathTokens];
}

function createDefaultValueEntry(kind: ValueEntryKind = "string"): ValueEntry {
  switch (kind) {
    case "null":
      return createNullValueEntry();
    case "boolean":
      return createBooleanValueEntry(false);
    case "integer":
      return createIntegerValueEntry(0);
    case "number":
      return createNumberValueEntry(0);
    case "array":
      return createArrayValueEntry([]);
    case "object":
      return createObjectValueEntry([]);
    case "string":
    default:
      return createStringValueEntry("");
  }
}

export function createNullValueEntry(pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH): ValueEntryNull {
  return { kind: "null", pathTokens: createValueEntryPath(pathTokens), value: null } satisfies ValueEntryNull;
}

export function createBooleanValueEntry(
  value = false,
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryBoolean {
  return { kind: "boolean", pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryBoolean;
}

export function createIntegerValueEntry(
  value = 0,
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryInteger {
  return { kind: "integer", pathTokens: createValueEntryPath(pathTokens), value: Math.trunc(value) } satisfies ValueEntryInteger;
}

export function createNumberValueEntry(
  value = 0,
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryNumber {
  return { kind: "number", pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryNumber;
}

export function createStringValueEntry(
  value = "",
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryString {
  return { kind: "string", pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryString;
}

export function createArrayValueEntry(items: ValueEntryArrayItem[] = [], pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH): ValueEntryArray {
  return { kind: "array", pathTokens: createValueEntryPath(pathTokens), items } satisfies ValueEntryArray;
}

export function createObjectValueEntry(fields: ValueEntryObjectField[] = [], pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH): ValueEntryObject {
  return { kind: "object", pathTokens: createValueEntryPath(pathTokens), fields } satisfies ValueEntryObject;
}

export function createValueEntryArrayItem(
  index: number,
  value: ValueEntry = createDefaultValueEntry("string"),
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryArrayItem {
  return { index, pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryArrayItem;
}

export function createValueEntryObjectField(
  key: string,
  value: ValueEntry = createDefaultValueEntry("string"),
  pathTokens: ValueEntryPath = DEFAULT_VALUE_ENTRY_PATH,
): ValueEntryObjectField {
  return { key, pathTokens: createValueEntryPath(pathTokens), value } satisfies ValueEntryObjectField;
}

function extendPath(pathTokens: ValueEntryPath, token: string): ValueEntryPath {
  return [...pathTokens, token];
}

function hasSchemaDefault(schema: SchemaIRNode): boolean {
  return Object.prototype.hasOwnProperty.call(schema, "defaultValue");
}

function isRecord(value: JsonValue): value is { [key: string]: JsonValue } {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function getPrimitiveValue(value: ValueEntry): JsonPrimitive | null | undefined {
  switch (value.kind) {
    case "null":
    case "boolean":
    case "integer":
    case "number":
    case "string":
      return value.value;
    case "array":
    case "object":
      return undefined;
  }
}

export function createPrimitiveValueEntry(value: JsonPrimitive | null, pathTokens: ValueEntryPath): ValueEntryScalar {
  if (value === null) {
    return createNullValueEntry(pathTokens);
  }

  switch (typeof value) {
    case "boolean":
      return createBooleanValueEntry(value, pathTokens);
    case "number":
      return Number.isInteger(value) ? createIntegerValueEntry(value, pathTokens) : createNumberValueEntry(value, pathTokens);
    case "string":
      return createStringValueEntry(value, pathTokens);
  }
}

export function rebaseValueEntryPaths(value: ValueEntry, pathTokens: ValueEntryPath): ValueEntry {
  switch (value.kind) {
    case "null":
    case "boolean":
    case "integer":
    case "number":
    case "string":
      return createPrimitiveValueEntry(value.value, pathTokens);
    case "array":
      return createArrayValueEntry(
        value.items.map((item, index) => {
          const itemPath = extendPath(pathTokens, String(index));
          return createValueEntryArrayItem(index, rebaseValueEntryPaths(item.value, itemPath), itemPath);
        }),
        pathTokens,
      );
    case "object":
      return createObjectValueEntry(
        value.fields.map((field) => {
          const fieldPath = extendPath(pathTokens, field.key);
          return createValueEntryObjectField(field.key, rebaseValueEntryPaths(field.value, fieldPath), fieldPath);
        }),
        pathTokens,
      );
  }
}

function createValueEntryFromJsonValue(value: JsonValue, pathTokens: ValueEntryPath): ValueEntry {
  if (value === null || typeof value === "boolean" || typeof value === "number" || typeof value === "string") {
    return createPrimitiveValueEntry(value, pathTokens);
  }

  if (Array.isArray(value)) {
    return createArrayValueEntry(
      value.map((item, index) => {
        const itemPath = extendPath(pathTokens, String(index));
        return createValueEntryArrayItem(index, createValueEntryFromJsonValue(item, itemPath), itemPath);
      }),
      pathTokens,
    );
  }

  return createObjectValueEntry(
    Object.entries(value).map(([key, entryValue]) => {
      const fieldPath = extendPath(pathTokens, key);
      return createValueEntryObjectField(key, createValueEntryFromJsonValue(entryValue, fieldPath), fieldPath);
    }),
    pathTokens,
  );
}

function createScalarValueEntryForSchemaDefault(schema: SchemaIRNode, value: JsonValue, pathTokens: ValueEntryPath): ValueEntry | null {
  switch (schema.kind) {
    case "string":
      return typeof value === "string" ? createStringValueEntry(value, pathTokens) : null;
    case "integer":
      return typeof value === "number" && Number.isInteger(value) ? createIntegerValueEntry(value, pathTokens) : null;
    case "number":
      return typeof value === "number" ? createNumberValueEntry(value, pathTokens) : null;
    case "boolean":
      return typeof value === "boolean" ? createBooleanValueEntry(value, pathTokens) : null;
    case "enum":
      return value !== null && !Array.isArray(value) && !isRecord(value) ? createPrimitiveValueEntry(value, pathTokens) : null;
    case "literal":
      return createPrimitiveValueEntry(schema.value, pathTokens);
    default:
      return null;
  }
}

function getDefaultedUnionVariant(schema: SchemaIRDiscriminatedUnion, value: JsonValue): SchemaIRNode {
  if (isRecord(value)) {
    const selectedVariant = schema.variants.find((variant) => {
      if (variant.kind !== "object") {
        return false;
      }

      const discriminatorField = (variant.fields ?? []).find((field) => field.name === schema.discriminator);
      return discriminatorField?.schema.kind === "literal" && value[schema.discriminator] === discriminatorField.schema.value;
    });

    if (selectedVariant) {
      return selectedVariant;
    }
  }

  return schema.variants[0] ?? { kind: "object", fields: [] };
}

function createValueEntryFromDefaultValue(schema: SchemaIRNode, value: JsonValue, pathTokens: ValueEntryPath): ValueEntry {
  const scalarEntry = createScalarValueEntryForSchemaDefault(schema, value, pathTokens);
  if (scalarEntry) {
    return scalarEntry;
  }

  if (schema.kind === "array" && Array.isArray(value)) {
    return createArrayValueEntry(
      value.map((item, index) => {
        const itemPath = extendPath(pathTokens, String(index));
        return createValueEntryArrayItem(index, createValueEntryFromDefaultValue(schema.items, item, itemPath), itemPath);
      }),
      pathTokens,
    );
  }

  if (schema.kind === "object" && isRecord(value)) {
    const fields = schema.fields ?? [];
    const defaultedFields = fields
      .filter((field) => Object.prototype.hasOwnProperty.call(value, field.name))
      .map((field) => {
        const fieldPath = extendPath(pathTokens, field.name);
        const fieldValue = createValueEntryFromDefaultValue(field.schema, value[field.name], fieldPath);
        return createValueEntryObjectField(field.name, fieldValue, fieldPath);
      });
    return createObjectValueEntry(defaultedFields, pathTokens);
  }

  if (schema.kind === "discriminated_union") {
    return createValueEntryFromDefaultValue(getDefaultedUnionVariant(schema, value), value, pathTokens);
  }

  if (schema.kind === "ref") {
    return createValueEntryFromJsonValue(value, pathTokens);
  }

  if (schema.kind === "integer") {
    return createIntegerValueEntry(0, pathTokens);
  }

  if (schema.kind === "number") {
    return createNumberValueEntry(0, pathTokens);
  }

  return createStringValueEntry("", pathTokens);
}

export function createValueEntryForSchema(schema: SchemaIRNode, pathTokens: ValueEntryPath = []): ValueEntry {
  if (hasSchemaDefault(schema)) {
    return createValueEntryFromDefaultValue(schema, schema.defaultValue as JsonValue, pathTokens);
  }

  switch (schema.kind) {
    case "string":
      return createStringValueEntry("", pathTokens);
    case "integer":
      return createIntegerValueEntry(0, pathTokens);
    case "number":
      return createNumberValueEntry(0, pathTokens);
    case "boolean":
      return createBooleanValueEntry(false, pathTokens);
    case "enum":
      return createPrimitiveValueEntry(schema.values[0] ?? "", pathTokens);
    case "literal":
      return createPrimitiveValueEntry(schema.value, pathTokens);
    case "array":
      return createArrayValueEntry([], pathTokens);
    case "ref":
      return createStringValueEntry("", pathTokens);
    case "discriminated_union":
      return createValueEntryForSchema(schema.variants[0] ?? { kind: "object", fields: [] }, pathTokens);
    case "object":
    default:
      return createObjectValueEntry(
        (schema.fields ?? [])
          .filter((field) => field.required !== false || hasSchemaDefault(field.schema))
          .map((field) => {
            const fieldPath = extendPath(pathTokens, field.name);
            return createValueEntryObjectField(field.name, createValueEntryForSchema(field.schema, fieldPath), fieldPath);
          }),
        pathTokens,
      );
  }
}

function isEnumValueAllowed(schema: Extract<SchemaIRNode, { kind: "enum" }>, value: ValueEntry): boolean {
  const primitiveValue = getPrimitiveValue(value);
  return primitiveValue != null && schema.values.some((option) => option === primitiveValue);
}

export function coerceValueEntryForSchema(schema: SchemaIRNode, value: ValueEntry | null | undefined, pathTokens: ValueEntryPath = []): ValueEntry {
  switch (schema.kind) {
    case "string":
      return value?.kind === "string" ? createStringValueEntry(value.value, pathTokens) : createValueEntryForSchema(schema, pathTokens);
    case "integer":
      if (value?.kind === "integer") {
        return createIntegerValueEntry(value.value, pathTokens);
      }
      if (value?.kind === "number" && Number.isInteger(value.value)) {
        return createIntegerValueEntry(value.value, pathTokens);
      }
      return createValueEntryForSchema(schema, pathTokens);
    case "number":
      if (value?.kind === "number" || value?.kind === "integer") {
        return createNumberValueEntry(value.value, pathTokens);
      }
      return createValueEntryForSchema(schema, pathTokens);
    case "boolean":
      return value?.kind === "boolean" ? createBooleanValueEntry(value.value, pathTokens) : createValueEntryForSchema(schema, pathTokens);
    case "enum":
      return value && isEnumValueAllowed(schema, value)
        ? createPrimitiveValueEntry(getPrimitiveValue(value) ?? schema.values[0] ?? "", pathTokens)
        : createValueEntryForSchema(schema, pathTokens);
    case "literal":
      return createPrimitiveValueEntry(schema.value, pathTokens);
    case "array":
      if (value?.kind !== "array") {
        return createValueEntryForSchema(schema, pathTokens);
      }
      return createArrayValueEntry(
        value.items.map((item, index) => {
          const itemPath = extendPath(pathTokens, String(index));
          return createValueEntryArrayItem(index, coerceValueEntryForSchema(schema.items, item.value, itemPath), itemPath);
        }),
        pathTokens,
      );
    case "ref":
      return value ? rebaseValueEntryPaths(value, pathTokens) : createValueEntryForSchema(schema, pathTokens);
    case "discriminated_union": {
      const selectedIndex = getSelectedDiscriminatedUnionIndex(schema, value);
      return coerceValueEntryForSchema(schema.variants[selectedIndex] ?? schema.variants[0] ?? { kind: "object", fields: [] }, value, pathTokens);
    }
    case "object": {
      const objectValue = value?.kind === "object" ? value : undefined;
      const knownFields = schema.fields ?? [];
      const knownFieldNames = new Set(knownFields.map((field) => field.name));
      const existingFields = new Map(objectValue?.fields.map((field) => [field.key, field]));
      const nextFields = knownFields
        .filter((field) => field.required !== false || existingFields.has(field.name) || hasSchemaDefault(field.schema))
        .map((field) => {
          const fieldPath = extendPath(pathTokens, field.name);
          return createValueEntryObjectField(
            field.name,
            coerceValueEntryForSchema(field.schema, existingFields.get(field.name)?.value, fieldPath),
            fieldPath,
          );
        });
      const extraFields = (objectValue?.fields ?? [])
        .filter((field) => !knownFieldNames.has(field.key))
        .map((field) => {
          const fieldPath = extendPath(pathTokens, field.key);
          return createValueEntryObjectField(field.key, rebaseValueEntryPaths(field.value, fieldPath), fieldPath);
        });

      return createObjectValueEntry([...nextFields, ...extraFields], pathTokens);
    }
  }
}

function getSelectedDiscriminatedUnionIndex(schema: SchemaIRDiscriminatedUnion, value: ValueEntry | null | undefined): number {
  if (!value || value.kind !== "object") {
    return 0;
  }

  const discriminatorField = value.fields.find((field) => field.key === schema.discriminator);
  const discriminatorValue = discriminatorField ? getPrimitiveValue(discriminatorField.value) : undefined;
  if (discriminatorValue == null) {
    return 0;
  }

  const selectedIndex = schema.variants.findIndex((variant) => {
    if (variant.kind !== "object") {
      return false;
    }

    const discriminatorSchema = (variant.fields ?? []).find((field) => field.name === schema.discriminator)?.schema;
    return discriminatorSchema?.kind === "literal" && discriminatorSchema.value === discriminatorValue;
  });

  return selectedIndex >= 0 ? selectedIndex : 0;
}
