import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
import { ValueEditor } from "./value-editor";

Object.defineProperty(HTMLElement.prototype, "hasPointerCapture", {
  configurable: true,
  value: () => false,
});
Object.defineProperty(HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});

function Editor({ initial, schema }: { initial: Json; schema?: JsonObject }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <ValueEditor
        label="内容"
        value={value}
        schema={schema}
        onChange={setValue}
      />
      <output>{JSON.stringify(value)}</output>
    </>
  );
}
function select(label: string, choice: string) {
  fireEvent.keyDown(screen.getByLabelText(label), { key: "ArrowDown" });
  fireEvent.click(screen.getByRole("option", { name: choice }));
}
function payload() {
  return JSON.parse(screen.getByRole("status").textContent!);
}

it("preserves exact omitted, empty and null values while editing an array sibling", () => {
  render(
    <Editor
      initial={{
        items: [
          { title: "first", legacy: { untouched: null } },
          { title: "second", blank: "" },
        ],
      }}
      schema={{
        type: "object",
        properties: {
          items: {
            type: "array",
            items: {
              type: "object",
              properties: {
                title: { type: "string" },
                blank: { type: "string" },
                optional: {
                  type: "string",
                  "x-signaldeck-schema": "signaldeck.schema/2",
                  default: "never add",
                },
              },
              required: ["title"],
            },
          },
        },
        required: ["items"],
      }}
    />,
  );
  fireEvent.change(screen.getAllByLabelText("title")[1], {
    target: { value: "edited" },
  });
  expect(payload()).toEqual({
    items: [
      { title: "first", legacy: { untouched: null } },
      { title: "edited", blank: "" },
    ],
  });
  expect(
    screen.getByText("当前任务不再使用此项。内容仍保留，请核对后移除。"),
  ).toBeVisible();
});

it("makes compound choice contents visible and retains the chosen object exactly", () => {
  render(
    <Editor
      initial={{ title: "first", items: [1, 2] }}
      schema={{
        type: "object",
        properties: {
          title: { type: "string", title: "标题" },
          items: { type: "array", items: { type: "integer" } },
        },
        enum: [
          { title: "first", items: [1, 2] },
          { title: "second", items: [] },
        ],
      }}
    />,
  );
  expect(screen.getByText("second")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "选择选项 2" }));
  expect(payload()).toEqual({ title: "second", items: [] });
});

it("allows free values to change form and restore their earlier contents", () => {
  render(<Editor initial={"  original\n"} />);
  select("内容内容类型", "列表");
  fireEvent.click(screen.getByRole("button", { name: "添加项目" }));
  fireEvent.change(screen.getByLabelText("第 1 项"), {
    target: { value: "list entry" },
  });
  expect(payload()).toEqual(["list entry"]);
  select("内容内容类型", "文字");
  expect(payload()).toBe("  original\n");
  select("内容内容类型", "列表");
  expect(payload()).toEqual(["list entry"]);
});

it("lets a missing boolean be explicitly answered no without adding other defaults", () => {
  render(
    <Editor
      initial={{}}
      schema={{
        type: "object",
        properties: {
          approved: { type: "boolean", title: "同意" },
          omitted: {
            type: "string",
            "x-signaldeck-schema": "signaldeck.schema/2",
            default: "keep omitted",
          },
        },
        required: ["approved"],
      }}
    />,
  );
  select("同意", "否");
  expect(payload()).toEqual({ approved: false });
});

it("preserves nullable values across edits and restores the previous nonempty alternative", () => {
  render(<Editor initial="saved" schema={{ type: ["string", "null"] }} />);
  select("内容填写方式", "空值");
  expect(payload()).toBeNull();
  select("内容填写方式", "文字");
  expect(payload()).toBe("saved");
});

it("reports bounds and uniqueness in business language", () => {
  render(
    <Editor
      initial={[{ n: 2 }, { n: 2 }]}
      schema={{
        type: "array",
        items: {
          type: "object",
          properties: { n: { type: "integer", title: "数量", minimum: 3 } },
          required: ["n"],
        },
        uniqueItems: true,
      }}
    />,
  );
  expect(screen.getAllByText("请填写不小于 3 的数字。")).toHaveLength(2);
  expect(
    screen.getByText("列表中存在重复项目，请修改或移除重复项。"),
  ).toBeVisible();
  expect(screen.queryByText("minimum")).not.toBeInTheDocument();
});

it("keeps a cleared number empty through sibling edits instead of inserting zero", () => {
  render(
    <Editor
      initial={{ quantity: 12, note: "old" }}
      schema={{
        type: "object",
        properties: {
          quantity: { type: "number", title: "数量" },
          note: { type: "string", title: "说明" },
        },
        required: ["quantity", "note"],
      }}
    />,
  );
  fireEvent.change(screen.getByLabelText("数量"), { target: { value: "" } });
  expect(screen.getByLabelText("数量")).toHaveValue(null);
  fireEvent.change(screen.getByLabelText("说明"), {
    target: { value: "edited" },
  });
  expect(payload()).toEqual({ quantity: null, note: "edited" });
  expect(screen.getByLabelText("数量")).toHaveValue(null);
  expect(screen.getByText("请填写数字。")).toBeVisible();
  fireEvent.change(screen.getByLabelText("数量"), {
    target: { value: "0.25" },
  });
  expect(payload()).toEqual({ quantity: 0.25, note: "edited" });
});

it("orders fields by declared hints without renaming keys or changing payload order", () => {
  const change = vi.fn();
  const value = { body: "原文", title: "标题", extra: "保留" };
  render(
    <ValueEditor
      label="任务输入"
      value={value}
      schema={{
        type: "object",
        properties: {
          body: { type: "string", title: "正文" },
          title: { type: "string", title: "名称" },
          extra: { type: "string", title: "备注" },
        },
        required: ["body", "title", "extra"],
      }}
      inputHints={[
        { ref: "workflow.input.title", control: "text" },
        { ref: "workflow.input.body", control: "textarea" },
      ]}
      onChange={change}
    />,
  );
  expect(
    screen
      .getAllByRole("textbox")
      .map((element) => element.getAttribute("aria-label")),
  ).toEqual(["名称", "正文", "备注"]);
  fireEvent.change(screen.getByLabelText("名称"), {
    target: { value: "新标题" },
  });
  expect(change).toHaveBeenCalledWith({
    body: "原文",
    title: "新标题",
    extra: "保留",
  });
  expect(Object.keys(change.mock.calls[0][0])).toEqual([
    "body",
    "title",
    "extra",
  ]);
});

it("matches hints to the current object and array item rather than unrelated field names", () => {
  render(
    <ValueEditor
      value={{
        title: "root",
        entries: [{ body: "body", title: "item", extra: "extra" }],
      }}
      schema={{
        type: "object",
        properties: {
          title: { type: "string", title: "顶层名称" },
          entries: {
            type: "array",
            items: {
              type: "object",
              properties: {
                body: { type: "string", title: "项目正文" },
                title: { type: "string", title: "项目名称" },
                extra: { type: "string", title: "项目备注" },
              },
              required: ["body", "title", "extra"],
            },
          },
        },
        required: ["title", "entries"],
      }}
      inputHints={[
        { ref: "workflow.input.entries.0.title", control: "text" },
        { ref: "workflow.input.entries.0.body", control: "textarea" },
      ]}
      onChange={vi.fn()}
    />,
  );
  expect(
    screen
      .getAllByRole("textbox")
      .map((element) => element.getAttribute("aria-label")),
  ).toEqual(["项目名称", "项目正文", "项目备注", "顶层名称"]);
  expect(screen.getByLabelText("项目正文").tagName).toBe("TEXTAREA");
  expect(screen.getByLabelText("顶层名称").tagName).toBe("INPUT");
});

it("accepts new multiline text without requiring a predeclared textarea hint", () => {
  render(<Editor initial="" schema={{ type: "string", title: "内容" }} />);
  fireEvent.click(screen.getByRole("button", { name: "内容多行填写" }));
  expect(screen.getByLabelText("内容").tagName).toBe("TEXTAREA");
  fireEvent.change(screen.getByLabelText("内容"), { target: { value: "  first\n\nsecond  " } });
  expect(payload()).toBe("  first\n\nsecond  ");
});

it("describes allowed empty values without confusing stored presence with user effort", () => {
  const change = vi.fn();
  const value = { query: "", title: "", emptyList: [], neededList: [], nullable: null };
  render(<ValueEditor value={value} schema={{ type: "object", properties: {
    query: { type: "string", title: "查找范围" },
    title: { type: "string", title: "名称", minLength: 1 },
    emptyList: { type: "array", title: "附加项目", items: { type: "string" } },
    neededList: { type: "array", title: "目标项目", minItems: 1, items: { type: "string" } },
    nullable: { type: ["string", "null"], title: "留空说明" },
  }, required: ["query", "title", "emptyList", "neededList", "nullable"] }} inputHints={[{ ref: "workflow.input.query", control: "text", placeholder: "可留空" }]} onChange={change} />);
  for (const [label, requirement] of [["查找范围", "可留空"], ["名称", "必填"], ["附加项目", "可留空"], ["目标项目", "必填"]]) {
    const field = screen.getByText(label, { exact: true }).closest("section")!;
    expect(within(field).getByText(requirement, { exact: true })).toBeVisible();
  }
  expect(screen.getByText("允许空值", { exact: true })).toBeVisible();
  expect(screen.getByPlaceholderText("可留空")).toHaveValue("");
  expect(screen.queryByRole("button", { name: "移除查找范围" })).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("名称"), { target: { value: "新名称" } });
  expect(change).toHaveBeenCalledWith({ ...value, title: "新名称" });
});

it("treats nonempty-only choices as required even without a minimum length", () => {
  render(<ValueEditor value={{ selection: "ready" }} schema={{ type: "object", properties: { selection: { type: "string", title: "处理方式", enum: ["ready", "later"] } }, required: ["selection"] }} onChange={vi.fn()} />);
  const field = screen.getByText("处理方式", { exact: true }).closest("section")!;
  expect(within(field).getByText("必填", { exact: true })).toBeVisible();
  expect(within(field).queryByText("可留空", { exact: true })).not.toBeInTheDocument();
});
