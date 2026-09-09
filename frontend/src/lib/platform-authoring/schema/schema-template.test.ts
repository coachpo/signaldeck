import { describe, expect, it } from "vitest";

import {
  createLaunchParametersTemplate,
  parseLaunchParametersJson,
  resetLaunchParametersTemplate,
} from "./schema-template";

describe("launch schema templates", () => {
  const schema = {
    properties: {
      optionalNote: { title: "Optional Note", type: "string" },
      ticker: { title: "Ticker", type: "string" },
      limit: { "x-signaldeck-schema": "signaldeck.schema/2", default: 10, title: "Limit", type: "integer" },
      filters: {
        properties: {
          includeNews: { "x-signaldeck-schema": "signaldeck.schema/2", default: true, type: "boolean" },
          ignoredOptional: { type: "string" },
          sector: { type: "string" },
        },
        required: ["sector"],
        type: "object",
      },
    },
    required: ["ticker", "filters"],
    type: "object",
  };

  it("derives deterministic JSON from required and defaulted schema fields", () => {
    const first = createLaunchParametersTemplate(schema);
    const second = createLaunchParametersTemplate(schema);

    expect(first.schemaSupported).toBe(true);
    expect(first.parameters).toEqual({
      filters: { includeNews: true, sector: "" },
      limit: 10,
      ticker: "",
    });
    expect(first.text).toBe(second.text);
    expect(first.text).toBe(JSON.stringify(first.parameters, null, 2));
  });

  it("resets back to the exact generated template text", () => {
    const template = createLaunchParametersTemplate(schema);

    expect(resetLaunchParametersTemplate(template)).toBe(template.text);
  });

  it("starts unsupported or non-object schemas from an empty object template", () => {
    expect(createLaunchParametersTemplate({ type: "string" })).toMatchObject({
      parameters: {},
      schemaSupported: false,
    });
    expect(createLaunchParametersTemplate({ additionalProperties: true, type: "object" })).toMatchObject({
      parameters: {},
      schemaSupported: false,
    });
  });

  it("parses only object JSON launch parameters", () => {
    expect(parseLaunchParametersJson("{\"ticker\":\"AAPL\"}")).toEqual({ ticker: "AAPL" });
    expect(() => parseLaunchParametersJson("[]")).toThrow("Runtime inputs JSON must be a valid object.");
  });

  it("preserves explicit nulls in parsed launch parameter JSON", () => {
    expect(parseLaunchParametersJson("{\"optionalNote\":null,\"ticker\":\"AAPL\"}")).toEqual({
      optionalNote: null,
      ticker: "AAPL",
    });
  });
});
