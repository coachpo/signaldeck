import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { expect, it } from "vitest";
import { TaskInputs } from "./task-inputs";
import {
  supportsTaskForm,
  taskConstraintErrors,
  taskDefaults,
  taskDescriptor,
} from "./task-catalog";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
function Form({ schema, initial }: { schema: JsonObject; initial: Json }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <TaskInputs schema={schema} value={value} onChange={setValue} />
      <output>{JSON.stringify(value)}</output>
    </>
  );
}
it("edits the original text without normalization or a raw input decision", () => {
  render(
    <Form
      schema={{
        type: "object",
        properties: { title: { type: "string" }, text: { type: "string" } },
        required: ["title", "text"],
      }}
      initial={{ title: "", text: "" }}
    />,
  );
  fireEvent.change(screen.getByLabelText("原文"), {
    target: { value: "  原文\n\n保持  " },
  });
  expect(JSON.parse(screen.getByRole("status").textContent!)).toEqual({
    title: "",
    text: "  原文\n\n保持  ",
  });
  expect(screen.queryByText(/JSON/)).not.toBeInTheDocument();
});
it("keeps null, omitted values and unknown fields until explicitly changed", () => {
  render(
    <Form
      schema={{
        type: "object",
        properties: {
          title: { type: "string" },
          query: { type: ["string", "null"] },
        },
        required: ["title"],
      }}
      initial={{ title: "原题", query: null, legacy: "keep" }}
    />,
  );
  fireEvent.change(screen.getByLabelText("标题"), {
    target: { value: "新题" },
  });
  expect(screen.getByRole("status")).toHaveTextContent(
    '"query":null,"legacy":"keep"',
  );
  fireEvent.click(screen.getByLabelText("填写查找已有笔记（可选）"));
  expect(screen.getByRole("status")).toHaveTextContent(
    '{"title":"新题","legacy":"keep"}',
  );
});
it("adds and removes array items without delimiter parsing", () => {
  render(
    <Form
      schema={{
        type: "object",
        properties: { symbols: { type: "array", items: { type: "string" } } },
        required: ["symbols"],
      }}
      initial={{ symbols: ["A,B"] }}
    />,
  );
  fireEvent.click(screen.getByText("添加研究对象"));
  fireEvent.change(screen.getByLabelText("研究对象 2"), {
    target: { value: "C" },
  });
  expect(screen.getByRole("status")).toHaveTextContent('"symbols":["A,B","C"]');
});
it("defaults risk on while respecting authored false defaults", () => {
  const schema: JsonObject = {
    type: "object",
    properties: { includeRisk: { type: "boolean" } },
    required: ["includeRisk"],
  };
  expect(taskDefaults(schema)).toEqual({ includeRisk: true });
  expect(
    taskDefaults({
      ...schema,
      default: null,
      properties: { includeRisk: { type: "boolean", default: null } },
    }),
  ).toEqual({ includeRisk: true });
  expect(
    taskDefaults({
      ...schema,
      properties: { includeRisk: { type: "boolean", default: false } },
    }),
  ).toEqual({ includeRisk: false });
});
it("routes changed scenario fields to experts and validates visible constraints", () => {
  const schema: JsonObject = {
    type: "object",
    properties: {
      title: { type: "string", minLength: 1 },
      text: { type: "string" },
    },
    required: ["title", "text"],
  };
  expect(
    supportsTaskForm(taskDescriptor("research_notes", "capture"), schema),
  ).toBe(true);
  expect(
    supportsTaskForm(taskDescriptor("research_notes", "capture"), {
      ...schema,
      properties: {
        ...(schema.properties as JsonObject),
        extra: { type: "string" },
      },
    }),
  ).toBe(false);
  expect(taskConstraintErrors(schema, { title: "", text: "" })).toEqual({
    "parameters.title": "请至少填写 1 个字符。",
  });
});

it("defaults the complete market contract risk to true", () => {
  expect(
    taskDefaults({
      type: "object",
      required: ["symbols", "question", "includeRisk"],
      properties: {
        symbols: {
          type: "array",
          items: { type: "string" },
          maxItems: 10,
          minItems: 1,
        },
        question: { type: "string", minLength: 1 },
        includeRisk: { type: "boolean" },
      },
    }),
  ).toEqual({ symbols: [], question: "", includeRisk: true });
});
