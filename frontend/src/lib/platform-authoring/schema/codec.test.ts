import { describe, expect, it } from "vitest";

import {
  parseSchemaJsonObject,
  parseSchemaJsonText,
  schemaBuilderToJsonSchema,
  validateSchemaDefaultValue,
} from "./codec";

type SchemaBuilderInput = Parameters<typeof schemaBuilderToJsonSchema>[0];
type JsonDefaultValue = null | boolean | number | string | JsonDefaultValue[] | { [key: string]: JsonDefaultValue };

function builderWithDefault(builder: SchemaBuilderInput, defaultValue: JsonDefaultValue): SchemaBuilderInput {
  return { ...builder, annotationVersion: "signaldeck.schema/2", defaultValue } as unknown as SchemaBuilderInput;
}

const metadataRichBuilder = {
  kind: "object",
  title: "Run Input",
  description: "Fields collected before launching the run.",
  fields: [
    {
      name: "summary",
      required: true,
      schema: { kind: "string", title: "Summary", description: "Short text entered by the operator." },
    },
    {
      name: "approved",
      required: false,
      schema: { kind: "boolean", title: "Approved", description: "Whether the run may proceed." },
    },
    {
      name: "score",
      required: true,
      schema: { kind: "number", title: "Score", description: "Confidence score for the run." },
    },
    {
      name: "count",
      required: true,
      schema: { kind: "integer", title: "Count", description: "Number of positions to review." },
    },
    {
      name: "itemIds",
      required: true,
      schema: {
        kind: "array",
        title: "Item IDs",
        description: "Identifiers selected for the run.",
        items: { kind: "integer", title: "Item ID", description: "Single identifier." },
      },
    },
    {
      name: "rating",
      required: true,
      schema: { kind: "enum", values: ["low", "high"], title: "Rating", description: "Allowed rating values." },
    },
    {
      name: "status",
      required: true,
      schema: { kind: "literal", value: "ready", title: "Status", description: "Fixed status marker." },
    },
    {
      name: "shared",
      required: true,
      schema: {
        kind: "ref",
        schemaKey: "analysis_schema",
        schemaVersion: 2,
        title: "Shared Schema",
        description: "Registry-backed shared schema.",
      },
    },
    {
      name: "event",
      required: true,
      schema: {
        kind: "discriminated_union",
        title: "Event",
        description: "Event-specific input payload.",
        discriminator: "kind",
        variants: [
          {
            kind: "object",
            title: "Buy Event",
            description: "Branch for buy orders.",
                      fields: [
              {
                name: "kind",
                required: true,
                schema: { kind: "literal", value: "buy", title: "Event Kind", description: "Discriminator value." },
              },
              {
                name: "confidence",
                required: true,
                schema: { kind: "number", title: "Confidence", description: "Branch confidence value." },
              },
            ],
          },
          {
            kind: "object",
            title: "Sell Event",
            description: "Branch for sell orders.",
                      fields: [
              {
                name: "kind",
                required: true,
                schema: { kind: "literal", value: "sell", title: "Event Kind", description: "Discriminator value." },
              },
              {
                name: "reason",
                required: true,
                schema: { kind: "string", title: "Reason", description: "Branch reason text." },
              },
            ],
          },
        ],
      },
    },
  ],
} satisfies SchemaBuilderInput;

const metadataRichJsonSchema = {
  properties: {
    summary: { type: "string", title: "Summary", description: "Short text entered by the operator." },
    approved: { type: "boolean", title: "Approved", description: "Whether the run may proceed." },
    score: { type: "number", title: "Score", description: "Confidence score for the run." },
    count: { type: "integer", title: "Count", description: "Number of positions to review." },
    itemIds: {
      items: { type: "integer", title: "Item ID", description: "Single identifier." },
      type: "array",
      title: "Item IDs",
      description: "Identifiers selected for the run.",
    },
    rating: { enum: ["low", "high"], type: "string", title: "Rating", description: "Allowed rating values." },
    status: { const: "ready", type: "string", title: "Status", description: "Fixed status marker." },
    shared: {
      $ref: "registry://analysis_schema@2",
      title: "Shared Schema",
      description: "Registry-backed shared schema.",
    },
    event: {
      anyOf: [
        {
                  properties: {
            kind: { const: "buy", type: "string", title: "Event Kind", description: "Discriminator value." },
            confidence: { type: "number", title: "Confidence", description: "Branch confidence value." },
          },
          required: ["kind", "confidence"],
          type: "object",
          title: "Buy Event",
          description: "Branch for buy orders.",
        },
        {
                  properties: {
            kind: { const: "sell", type: "string", title: "Event Kind", description: "Discriminator value." },
            reason: { type: "string", title: "Reason", description: "Branch reason text." },
          },
          required: ["kind", "reason"],
          type: "object",
          title: "Sell Event",
          description: "Branch for sell orders.",
        },
      ],
      discriminator: { propertyName: "kind" },
      title: "Event",
      description: "Event-specific input payload.",
    },
  },
  required: ["summary", "score", "count", "itemIds", "rating", "status", "shared", "event"],
  type: "object",
  title: "Run Input",
  description: "Fields collected before launching the run.",
};

describe("schema codec", () => {
  it("writes title and description metadata for supported builder nodes", () => {
    expect(schemaBuilderToJsonSchema(metadataRichBuilder)).toEqual(metadataRichJsonSchema);
  });

  it("reads title and description metadata from supported JSON Schema nodes", () => {
    const result = parseSchemaJsonText(JSON.stringify(metadataRichJsonSchema, null, 2));

    expect(result.issues).toEqual([]);
    expect(result.builder).toEqual(metadataRichBuilder);
  });

  it("parses already-decoded JSON Schema objects through the shared schema parser", () => {
    const result = parseSchemaJsonObject(metadataRichJsonSchema);

    expect(result).toEqual({
      builder: metadataRichBuilder,
      issues: [],
      jsonSchema: metadataRichJsonSchema,
    });
  });

  it("returns structured parser failures for invalid already-decoded JSON Schema values", () => {
    const result = parseSchemaJsonObject({ type: "object", additionalProperties: { type: "string" } });

    expect(result).toEqual({
      builder: null,
      issues: [
        {
          field: "jsonSchema.additionalProperties",
          issue: "additionalProperties is not supported; objects are closed by default",
        },
      ],
      jsonSchema: null,
    });
  });

  it("writes primitive builder defaultValue entries as JSON Schema defaults", () => {
    expect(schemaBuilderToJsonSchema(builderWithDefault({ kind: "string" }, "AAPL"))).toEqual({
      "x-signaldeck-schema": "signaldeck.schema/2",
      default: "AAPL",
      type: "string",
    });
    expect(schemaBuilderToJsonSchema(builderWithDefault({ kind: "integer" }, 10))).toEqual({
      "x-signaldeck-schema": "signaldeck.schema/2",
      default: 10,
      type: "integer",
    });
    expect(schemaBuilderToJsonSchema(builderWithDefault({ kind: "number" }, 10.5))).toEqual({
      "x-signaldeck-schema": "signaldeck.schema/2",
      default: 10.5,
      type: "number",
    });
    expect(schemaBuilderToJsonSchema(builderWithDefault({ kind: "boolean" }, false))).toEqual({
      "x-signaldeck-schema": "signaldeck.schema/2",
      default: false,
      type: "boolean",
    });
  });

  it("round-trips nested object and array defaultValue entries through JSON Schema defaults", () => {
    const defaultedBuilder = builderWithDefault(
      {
        fields: [
          {
            name: "filters",
            required: false,
            schema: builderWithDefault(
              {
                fields: [{ name: "sector", required: false, schema: { kind: "string" } }],
                kind: "object",
              },
              { sector: "technology" },
            ),
          },
          {
            name: "lots",
            required: false,
            schema: builderWithDefault({ items: { kind: "integer" }, kind: "array" }, [10, 20]),
          },
          {
            name: "ticker",
            required: false,
            schema: builderWithDefault({ kind: "string", title: "Ticker" }, "AAPL"),
          },
        ],
        kind: "object",
      },
      { ticker: "MSFT", lots: [5], filters: {} },
    );
    const defaultedJsonSchema = {
      "x-signaldeck-schema": "signaldeck.schema/2",
      default: { ticker: "MSFT", lots: [5], filters: {} },
      properties: {
        filters: {
          "x-signaldeck-schema": "signaldeck.schema/2",
          default: { sector: "technology" },
          properties: { sector: { type: "string" } },
          required: [],
          type: "object",
        },
        lots: {
          "x-signaldeck-schema": "signaldeck.schema/2",
          default: [10, 20],
          items: { type: "integer" },
          type: "array",
        },
        ticker: { "x-signaldeck-schema": "signaldeck.schema/2", default: "AAPL", title: "Ticker", type: "string" },
      },
      required: [],
      type: "object",
    };

    expect(schemaBuilderToJsonSchema(defaultedBuilder)).toEqual(defaultedJsonSchema);

    const result = parseSchemaJsonText(JSON.stringify(defaultedJsonSchema, null, 2));

    expect(result.issues).toEqual([]);
    expect(result.builder).toEqual(defaultedBuilder);
  });

  it("reads primitive JSON Schema defaults into builder defaultValue entries", () => {
    const result = parseSchemaJsonText(
      JSON.stringify(
        {
          "x-signaldeck-schema": "signaldeck.schema/2",
          default: "AAPL",
          type: "string",
        },
        null,
        2,
      ),
    );

    expect(result.issues).toEqual([]);
    expect(result.builder).toEqual(builderWithDefault({ kind: "string", title: null, description: null }, "AAPL"));
  });

  it("rejects undeclared fields in closed object defaults", () => {
    const objectBuilder = {
      fields: [{ name: "ticker", required: false, schema: { kind: "string" } }],
      kind: "object",
    } satisfies SchemaBuilderInput;

    expect(
      validateSchemaDefaultValue(objectBuilder, {
        extra: { nested: ["ok"] },
        ticker: "AAPL",
      }),
    ).toEqual([{ field: "defaultValue.extra", issue: "Default object contains an unsupported field" }]);
    expect(validateSchemaDefaultValue(objectBuilder, { ticker: "AAPL" })).toEqual([]);
  });

  it("reports unsupported keywords with the current parser wording", () => {
    const result = parseSchemaJsonText(
      JSON.stringify(
        {
          type: "object",
          properties: {},
          patternProperties: { "^x": { type: "string" } },
        },
        null,
        2,
      ),
    );

    expect(result.builder).toBeNull();
    expect(result.jsonSchema).toBeNull();
    expect(result.issues).toEqual([
      {
        field: "jsonSchema.patternProperties",
        issue: "patternProperties is not supported",
      },
    ]);
  });

  it("decodes registry refs into key and version fields", () => {
    const result = parseSchemaJsonText(
      JSON.stringify(
        {
          $ref: "registry://shared_schema@12",
        },
        null,
        2,
      ),
    );

    expect(result.issues).toEqual([]);
    expect(result.builder).toEqual({
      kind: "ref",
      schemaKey: "shared_schema",
      schemaVersion: 12,
      title: null,
      description: null,
    });
  });
});

describe("versioned schema annotations", () => {
  it("requires per-node opt-in and never inherits the root marker", () => {
    const parsed = parseSchemaJsonObject({
      "x-signaldeck-schema": "signaldeck.schema/2", type: "object",
      properties: { arbitrary: { type: "string", default: "a" } },
    });
    expect(parsed.issues).toContainEqual(expect.objectContaining({ field: "jsonSchema.properties.arbitrary.default" }));
    expect(parseSchemaJsonObject({ type: "string", examples: ["a"] }).issues).not.toEqual([]);
  });
  it("preserves marker, empty examples and constraint declarations without adding annotations elsewhere", () => {
    const schema = { type: "array", minItems: 1, items: {
      "x-signaldeck-schema": "signaldeck.schema/2", type: "string", minLength: 1,
      default: "a", examples: [],
    } };
    const parsed = parseSchemaJsonObject(schema);
    expect(parsed.issues).toEqual([]);
    expect(schemaBuilderToJsonSchema(parsed.builder!)).toEqual(schema);
    const legacy = parseSchemaJsonObject({ type: "string" });
    expect(schemaBuilderToJsonSchema(legacy.builder!)).toEqual({ type: "string" });
  });
  it("validates examples and defaults against preserved constraints", () => {
    const parsed = parseSchemaJsonObject({ "x-signaldeck-schema": "signaldeck.schema/2", type: "string", minLength: 2, default: "a", examples: ["valid", ""] });
    expect(parsed.issues.map((issue) => issue.field)).toEqual(["jsonSchema.default", "jsonSchema.examples[1]"]);
    expect(parseSchemaJsonObject({ type: "string", minLength: -1 }).issues).not.toEqual([]);
  });
  it("keeps explicit null as an error for a non-nullable scalar rather than silently omitting it", () => {
    expect(parseSchemaJsonObject({ "x-signaldeck-schema": "signaldeck.schema/2", type: "string", default: null }).issues).toContainEqual(expect.objectContaining({ field: "jsonSchema.default" }));
  });
});
