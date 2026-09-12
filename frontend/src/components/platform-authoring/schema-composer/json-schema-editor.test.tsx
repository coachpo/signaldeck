import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { JsonObject } from "@/lib/types/workflow-platform";
import { JsonSchemaEditor } from "./json-schema-editor";

Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", {
  configurable: true,
  value: () => false,
});
Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});
function Editor({ initial }: { initial: JsonObject }) {
  const [schema, setSchema] = useState(initial);
  return (
    <>
      <JsonSchemaEditor label="任务输入" schema={schema} onChange={setSchema} />
      <output>{JSON.stringify(schema)}</output>
    </>
  );
}
function payload() {
  return JSON.parse(screen.getByRole("status").textContent!);
}

it("edits business field names without changing saved keys, values or closed constraints", () => {
  const initial = {
    type: "object",
    title: "资料",
    unevaluatedProperties: false,
    minProperties: 1,
    required: ["internal_name"],
    properties: {
      internal_name: {
        type: "string",
        title: "标题",
        maxLength: 20,
        "x-signaldeck-schema": "signaldeck.schema/2",
        default: "原值",
        examples: ["例子"],
      },
    },
  };
  render(<Editor initial={initial} />);
  fireEvent.change(screen.getByLabelText("字段 1名称"), {
    target: { value: "文章标题" },
  });
  expect(payload()).toEqual({
    ...initial,
    properties: {
      internal_name: { ...initial.properties.internal_name, title: "文章标题" },
    },
  });
  expect(screen.queryByDisplayValue("internal_name")).not.toBeInTheDocument();
  expect(
    screen.queryByText(/schema\/2|JSON|unevaluatedProperties/, {
      selector: "section *",
    }),
  ).not.toBeInTheDocument();
});

it("creates a null default with the correct annotation and no raw editor", () => {
  render(<Editor initial={{ type: "null", title: "无需填写" }} />);
  fireEvent.click(screen.getByRole("switch", { name: "无需填写预填内容" }));
  expect(payload()).toEqual({
    type: "null",
    title: "无需填写",
    default: null,
    "x-signaldeck-schema": "signaldeck.schema/2",
  });
  expect(screen.getByText("此项为空值，无需填写。")).toBeVisible();
  fireEvent.click(screen.getByRole("switch", { name: "无需填写预填内容" }));
  expect(payload()).not.toHaveProperty("default");
  expect(payload()).toHaveProperty(
    "x-signaldeck-schema",
    "signaldeck.schema/2",
  );
});

it("edits compound default values without adding omitted sibling defaults", () => {
  render(
    <Editor
      initial={{
        type: "object",
        properties: {
          title: { type: "string", title: "正文" },
          extra: {
            type: "string",
            "x-signaldeck-schema": "signaldeck.schema/2",
            default: "seed",
          },
        },
        required: ["title"],
        "x-signaldeck-schema": "signaldeck.schema/2",
        default: { title: "old" },
        examples: [{ title: "sample" }],
      }}
    />,
  );
  fireEvent.change(screen.getAllByLabelText("正文")[0], {
    target: { value: "new" },
  });
  expect(payload().default).toEqual({ title: "new" });
  expect(payload().examples).toEqual([{ title: "sample" }]);
});

it("adds fields with meaningful names and lets the author mark them optional", () => {
  render(<Editor initial={{ type: "object", properties: {} }} />);
  fireEvent.click(screen.getByRole("button", { name: "添加字段" }));
  fireEvent.change(screen.getByLabelText("字段 1名称"), {
    target: { value: "目的" },
  });
  fireEvent.click(screen.getByRole("switch", { name: "目的必填" }));
  expect(payload()).toEqual({
    type: "object",
    properties: { field_1: { type: "string", title: "目的" } },
    required: [],
  });
});
