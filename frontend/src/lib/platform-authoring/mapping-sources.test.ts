import { describe, expect, it } from "vitest";
import { changeConditionOperation, firstReference, renameMappingField, sourceForReference, sourceSchema } from "./mapping-sources";

describe("content source contracts", () => {
  const sources = [{ value: "agent.input", label: "助手收到的信息", schema: { type: "object", properties: {
    records: { type: "array", items: { type: "object", properties: { text: { type: "string" } } } },
  } } }];

  it("resolves a declared list item at an arbitrary index and preserves absent knowledge", () => {
    expect(sourceForReference(sources, "agent.input.records.75.text")).toBe(sources[0]);
    expect(sourceSchema(sources[0], "agent.input.records.75.text")).toEqual({ type: "string" });
    expect(sourceSchema(sources[0], "agent.input.records.75.missing")).toBeUndefined();
    expect(sourceForReference(sources, "tool.output")).toBeUndefined();
  });

  it("finds distinct declared text choices, including later list positions", () => {
    expect(firstReference(sources, ["string"], true)).toBe("agent.input.records.0.text");
    expect(firstReference(sources, ["string"], true, ["agent.input.records.0.text"])).toBe("agent.input.records.1.text");
  });

  it("prevents field renaming from overwriting a sibling", () => {
    const fields = { first: { value: false }, second: { value: null } };
    expect(renameMappingField(fields, "first", "second")).toBe(fields);
    expect(renameMappingField(fields, "first", "renamed")).toEqual({ renamed: { value: false }, second: { value: null } });
  });

  it("keeps comparison operands and nonempty boolean groups when changing operators", () => {
    const operands = [{ value: 0 }, { value: false }];
    expect(changeConditionOperation({ op: "eq", args: operands }, "ne")).toEqual({ op: "ne", args: operands });
    expect(changeConditionOperation({ op: "eq", args: operands }, "all")).toEqual({ op: "all", args: [{ op: "eq", args: [{ value: "" }, { value: "" }] }] });
    expect(changeConditionOperation({ op: "eq", args: operands }, "exists")).toEqual({ op: "exists", args: [{ value: 0 }] });
  });
});
