import { describe, expect, it } from "vitest";

import {
  createLaunchDraftFromPayload,
  createLaunchDraftFromValidatedPayload,
  createLaunchInputState,
  createLaunchPayloadFromDraft,
  formatLaunchDraftJson,
  parseLaunchPayloadJson,
  reconcileLaunchDraftChange,
} from "./launch-input-state";
import {
  createBooleanValueEntry,
  createIntegerValueEntry,
  createObjectValueEntry,
  createStringValueEntry,
  createValueEntryObjectField,
} from "../values/factories";

describe("launch input state", () => {
  const schema = {
    properties: {
      comment: { title: "Comment", type: "string" },
      defaultLimit: { "x-signaldeck-schema": "signaldeck.schema/2", default: 10, title: "Default Limit", type: "integer" },
      filters: {
        properties: {
          includeNews: { "x-signaldeck-schema": "signaldeck.schema/2", default: true, type: "boolean" },
          ignoredOptional: { type: "string" },
          sector: { type: "string" },
        },
        required: ["sector"],
        type: "object",
      },
      ticker: { title: "Ticker", type: "string" },
    },
    required: ["ticker", "filters"],
    type: "object",
  };

  it("creates canonical state for required and defaulted fields", () => {
    const state = createLaunchInputState(schema);

    expect(state.schemaSupported).toBe(true);
    expect(state.payload).toEqual({
      defaultLimit: 10,
      filters: { includeNews: true, sector: "" },
      ticker: "",
    });
    expect(state.formattedJson).toBe(JSON.stringify(state.payload, null, 2));
  });

  it("keeps formatted JSON deterministic", () => {
    const first = createLaunchInputState(schema);
    const second = createLaunchInputState(schema);

    expect(formatLaunchDraftJson(first.draft!)).toBe(
      formatLaunchDraftJson(second.draft!),
    );
  });

  it("rejects missing required fields before applying payloads", () => {
    const state = createLaunchInputState(schema);

    const rejected = createLaunchDraftFromValidatedPayload(state, {});

    expect(rejected.draft).toBeNull();
    expect(rejected.issues).toEqual([
      { field: "parameters.filters", issue: "Field is required." },
      { field: "parameters.ticker", issue: "Field is required." },
    ]);
  });

  it("rejects unknown fields before applying supported object payloads", () => {
    const state = createLaunchInputState(schema);

    const rejected = createLaunchDraftFromValidatedPayload(state, {
      filters: { sector: "technology" },
      unsupportedField: true,
      ticker: "AAPL",
    });

    expect(rejected.draft).toBeNull();
    expect(rejected.issues).toEqual([
      {
        field: "parameters.unsupportedField",
        issue: "Extra inputs are not permitted.",
      },
    ]);
  });

  it("keeps optional fields and defaults absent in explicitly supplied payloads", () => {
    const state = createLaunchInputState(schema);

    const accepted = createLaunchDraftFromValidatedPayload(state, {
      filters: { sector: "technology" },
      ticker: "AAPL",
    });

    expect(accepted.issues).toEqual([]);
    expect(createLaunchPayloadFromDraft(accepted.draft!)).toEqual({
      filters: { sector: "technology" },
      ticker: "AAPL",
    });
  });

  it("rejects nested missing required fields and nested unknown fields", () => {
    const state = createLaunchInputState(schema);

    const rejected = createLaunchDraftFromValidatedPayload(state, {
      filters: { unsupportedFilter: true },
      ticker: "AAPL",
    });

    expect(rejected.draft).toBeNull();
    expect(rejected.issues).toEqual([
      {
        field: "parameters.filters.unsupportedFilter",
        issue: "Extra inputs are not permitted.",
      },
      { field: "parameters.filters.sector", issue: "Field is required." },
    ]);
  });

  it("drops optional schema keys from the canonical payload after form removal", () => {
    const state = createLaunchInputState(schema);
    const previous = createLaunchDraftFromPayload(state, {
      comment: "Operator memo",
      filters: { sector: "technology" },
      ticker: "AAPL",
    });
    const next = createObjectValueEntry([
      createValueEntryObjectField(
        "defaultLimit",
        createIntegerValueEntry(10, ["defaultLimit"]),
        ["defaultLimit"],
      ),
      createValueEntryObjectField(
        "filters",
        createObjectValueEntry([
          createValueEntryObjectField(
            "includeNews",
            createBooleanValueEntry(true, ["filters", "includeNews"]),
            ["filters", "includeNews"],
          ),
          createValueEntryObjectField(
            "sector",
            createStringValueEntry("technology", ["filters", "sector"]),
            ["filters", "sector"],
          ),
        ], ["filters"]),
        ["filters"],
      ),
      createValueEntryObjectField(
        "ticker",
        createStringValueEntry("AAPL", ["ticker"]),
        ["ticker"],
      ),
    ]);

    const reconciled = reconcileLaunchDraftChange(state, previous, next);

    expect(createLaunchPayloadFromDraft(reconciled)).toEqual({
      defaultLimit: 10,
      filters: { includeNews: true, sector: "technology" },
      ticker: "AAPL",
    });
  });

  it("roundtrips explicit nullable nulls for primitive enum object and array wrappers", () => {
    const nullableState = createLaunchInputState({
      properties: {
        maybeArray: { items: { type: "string" }, type: ["array", "null"] },
        maybeEnum: { enum: ["buy", "sell", null], type: ["string", "null"] },
        maybeObject: {
          properties: { nested: { type: "string" } },
          required: ["nested"],
          type: ["object", "null"],
        },
        maybeTicker: { type: ["string", "null"] },
      },
      required: ["maybeTicker", "maybeEnum", "maybeObject", "maybeArray"],
      type: "object",
    });

    const draft = createLaunchDraftFromPayload(nullableState, {
      maybeArray: null,
      maybeEnum: null,
      maybeObject: null,
      maybeTicker: null,
    });

    expect(nullableState.schemaSupported).toBe(true);
    expect(draft?.fields.map((field) => [field.key, field.value.kind])).toEqual(
      [
        ["maybeArray", "null"],
        ["maybeEnum", "null"],
        ["maybeObject", "null"],
        ["maybeTicker", "null"],
      ],
    );
    expect(createLaunchPayloadFromDraft(draft!)).toEqual({
      maybeArray: null,
      maybeEnum: null,
      maybeObject: null,
      maybeTicker: null,
    });
  });

  it("rejects non-nullable nulls before applying raw JSON to a draft", () => {
    const nullableState = createLaunchInputState({
      properties: {
        maybeTicker: { type: ["string", "null"] },
        requiredTicker: { type: "string" },
      },
      required: ["maybeTicker", "requiredTicker"],
      type: "object",
    });

    const rejected = createLaunchDraftFromValidatedPayload(nullableState, {
      maybeTicker: null,
      requiredTicker: null,
    });
    const accepted = createLaunchDraftFromValidatedPayload(nullableState, {
      maybeTicker: null,
      requiredTicker: "AAPL",
    });

    expect(rejected.draft).toBeNull();
    expect(rejected.issues).toEqual([
      {
        field: "parameters.requiredTicker",
        issue: "Null is only allowed for nullable runtime input fields.",
      },
    ]);
    expect(createLaunchPayloadFromDraft(accepted.draft!)).toEqual({
      maybeTicker: null,
      requiredTicker: "AAPL",
    });
  });

  it("preserves unknown fields and nullable nulls when metadata rebinds the draft", () => {
    const nullableState = createLaunchInputState({
      properties: {
        maybeTicker: { type: ["string", "null"] },
        requiredTicker: { type: "string" },
      },
      required: ["maybeTicker", "requiredTicker"],
      type: "object",
    });
    const previous = createLaunchDraftFromPayload(nullableState, {
      maybeTicker: null,
      requiredTicker: "AAPL",
      stale: "kept",
    });
    const next = createObjectValueEntry([
      createValueEntryObjectField(
        "maybeTicker",
        createStringValueEntry("", ["maybeTicker"]),
        ["maybeTicker"],
      ),
      createValueEntryObjectField(
        "requiredTicker",
        createStringValueEntry("MSFT", ["requiredTicker"]),
        ["requiredTicker"],
      ),
    ]);

    const reconciled = reconcileLaunchDraftChange(
      nullableState,
      previous,
      next,
    );

    expect(createLaunchPayloadFromDraft(reconciled)).toEqual({
      maybeTicker: null,
      requiredTicker: "MSFT",
      stale: "kept",
    });
  });

  it("keeps unsupported schemas on the raw JSON fallback path", () => {
    const state = createLaunchInputState({
      additionalProperties: true,
      properties: { ticker: { type: "string" } },
      type: "object",
    });
    const fallbackApply = createLaunchDraftFromValidatedPayload(state, {
      unsupportedField: true,
      ticker: "AAPL",
    });

    expect(state.schemaSupported).toBe(false);
    expect(state.draft).toBeNull();
    expect(state.payload).toEqual({});
    expect(state.reason).toMatch(/could not be converted/i);
    expect(fallbackApply).toEqual({ draft: null, issues: [] });
  });

  it("parses only object raw JSON payloads", () => {
    expect(parseLaunchPayloadJson('{"ticker":"AAPL"}')).toEqual({
      ticker: "AAPL",
    });
    expect(() => parseLaunchPayloadJson("[]")).toThrow(
      "Runtime inputs JSON must be a valid object.",
    );
  });
});
