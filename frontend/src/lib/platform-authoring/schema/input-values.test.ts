import { expect, it } from "vitest";
import { inputValueIssues, newInputValue } from "./input-values";

it("initializes every legal root and arbitrary constant without wrapping or supplementing it", () => {
  expect(newInputValue({ type: "null" })).toBeNull();
  expect(newInputValue({ type: "boolean" })).toBe(false);
  expect(newInputValue({ type: "integer" })).toBe(0);
  expect(newInputValue({ type: "number" })).toBe(0);
  expect(newInputValue({ type: "string" })).toBe("");
  expect(
    newInputValue({
      type: "array",
      items: { type: "string" },
      const: ["exact", "comma,value"],
    }),
  ).toEqual(["exact", "comma,value"]);
  expect(
    newInputValue({
      type: "object",
      properties: {
        extra: {
          type: "string",
          "x-signaldeck-schema": "signaldeck.schema/2",
          default: "never add",
        },
      },
      enum: [{}],
    }),
  ).toEqual({});
  expect(
    newInputValue({
      type: "object",
      "x-signaldeck-schema": "signaldeck.schema/2",
      default: {},
      properties: {
        title: {
          type: "string",
          "x-signaldeck-schema": "signaldeck.schema/2",
          default: "never add",
        },
      },
    }),
  ).toEqual({});
});

it("validates compound choices structurally regardless of object key order", () => {
  const schema = {
    type: "object",
    properties: { first: { type: "integer" }, second: { type: "null" } },
    enum: [{ first: 1, second: null }],
  };
  expect(inputValueIssues(schema, { second: null, first: 1 })).toEqual([]);
  expect(inputValueIssues(schema, { first: 2, second: null })[0].message).toBe(
    "请选择列表中的一个选项。",
  );
});

it("validates all supported numeric, text, collection and omission boundaries with labels", () => {
  expect(
    inputValueIssues(
      { type: "number", exclusiveMinimum: 2, exclusiveMaximum: 4 },
      2,
    )[0].message,
  ).toBe("请填写大于 2 的数字。");
  expect(
    inputValueIssues({ type: "number", exclusiveMaximum: 4 }, 4)[0].message,
  ).toBe("请填写小于 4 的数字。");
  expect(inputValueIssues({ type: "number", multipleOf: 0.1 }, 0.3)).toEqual(
    [],
  );
  expect(
    inputValueIssues({ type: "number", multipleOf: 0.1 }, 0.31)[0].message,
  ).toBe("请以 0.1 为间隔填写。");
  expect(inputValueIssues({ type: "string", maxLength: 1 }, "😀")).toEqual([]);
  expect(
    inputValueIssues(
      {
        type: "object",
        properties: { hidden: { type: "string", title: "标题" } },
        required: ["hidden"],
      },
      {},
    ),
  ).toEqual([{ label: "标题", path: ["hidden"], message: "请填写此项。" }]);
  expect(
    inputValueIssues(
      {
        type: "object",
        properties: { flag: { type: "boolean" } },
        minProperties: 1,
      },
      {},
    )[0].message,
  ).toBe("请至少填写 1 个字段。");
  expect(
    inputValueIssues({ type: "array", items: { type: "null" }, maxItems: 1 }, [
      null,
      null,
    ])[0].message,
  ).toBe("最多添加 1 项。");
});
