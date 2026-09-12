import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { JsonObject } from "@/lib/types/workflow-platform";
import { ConditionEditor, MappingEditor, type MappingSource } from "./package-mapping";

const sources: MappingSource[] = [{
  value: "workflow.input", label: "任务填写内容", schema: {
    type: "object", properties: {
      rows: { type: "array", title: "资料列表", items: { type: "object", properties: {
        summary: { type: "string", title: "摘要" }, title: { type: "string", title: "完整标题" },
      } } },
      __whole__: { type: "string", title: "特别说明" },
    },
  },
}, { value: "nodes.collect.output", label: "资料整理 · 完成内容", schema: { type: "string" } }];

function select(label: string, option: string) {
  fireEvent.click(screen.getByRole("combobox", { name: label }));
  fireEvent.click(screen.getByRole("option", { name: option }));
}

function editMapping(initial: JsonObject, condition = false) {
  const changed = vi.fn();
  function Editor() {
    const [value, setValue] = useState(initial);
    const props = { value, sources, onChange: (next: JsonObject) => { changed(next); setValue(next); } };
    return condition ? <ConditionEditor {...props} /> : <MappingEditor {...props} label="内容" />;
  }
  render(<Editor />);
  return changed;
}

describe("business content mapping", () => {
  it("selects named source fields and any list position without displaying internal references", () => {
    const changed = editMapping({ ref: "workflow.input.rows.2.summary", onMissing: { ref: "nodes.unavailable.output", onMissing: { value: "未提供" } } });
    expect(screen.getByRole("combobox", { name: "内容 · 内容 1" })).toHaveTextContent("资料列表");
    expect(screen.getByRole("combobox", { name: "内容 · 内容 3" })).toHaveTextContent("摘要");
    fireEvent.change(screen.getByLabelText("内容 · 第几项 2"), { target: { value: "8" } });
    expect(changed.mock.lastCall?.[0]).toEqual({ ref: "workflow.input.rows.7.summary", onMissing: { ref: "nodes.unavailable.output", onMissing: { value: "未提供" } } });
    select("内容 · 内容 3", "完整标题");
    expect(changed.mock.lastCall?.[0].ref).toBe("workflow.input.rows.7.title");
    expect(document.body.textContent).not.toMatch(/workflow\.input|nodes\.|onMissing/);
  });

  it("preserves a missing saved source until the user deliberately selects a replacement", () => {
    const changed = editMapping({ ref: "nodes.removed.output.old", onMissing: { value: false } });
    expect(screen.getByRole("combobox", { name: "内容 · 来源" })).toHaveTextContent("已保存的来源（当前不可用）");
    expect(changed).not.toHaveBeenCalled();
    select("内容 · 来源", "资料整理 · 完成内容");
    expect(changed.mock.lastCall?.[0]).toEqual({ ref: "nodes.collect.output", onMissing: { value: false } });
    expect(document.body.textContent).not.toContain("nodes.removed");
  });

  it("keeps literal objects and composed objects distinct while editing a sibling value", () => {
    const initial = { object: { note: { value: "原文" }, details: { value: { count: 0, enabled: false, absent: null, blank: "" } } } };
    const changed = editMapping(initial);
    fireEvent.change(screen.getByLabelText("note · 固定内容"), { target: { value: "修改后的正文" } });
    expect(changed.mock.lastCall?.[0]).toEqual({ object: { ...initial.object, note: { value: "修改后的正文" } } });
    expect(document.body.textContent).not.toMatch(/JSON|YAML|schema/);
  });

  it("does not confuse a business field named like a whole-object option with the whole object", () => {
    const changed = editMapping({ ref: "workflow.input" });
    select("内容 · 内容 1", "特别说明");
    expect(changed.mock.lastCall?.[0]).toEqual({ ref: "workflow.input.__whole__" });
  });

  it("reorders composed items without converting their nested values", () => {
    const first = { value: { exact: false } };
    const second = { ref: "nodes.collect.output", onMissing: { value: null } };
    const changed = editMapping({ array: [first, second] });
    fireEvent.click(screen.getByRole("button", { name: "内容第 2 项上移" }));
    expect(changed.mock.lastCall?.[0]).toEqual({ array: [second, first] });
  });

  it("edits a nested condition while retaining unrelated comparisons and all operator choices", () => {
    const unchanged = { op: "not", args: [{ op: "exists", args: [{ ref: "nodes.collect.output" }] }] };
    const changed = editMapping({ op: "all", args: [{ op: "gte", args: [{ value: 5 }, { value: 3 }] }, unchanged] }, true);
    select("执行条件 · 条件 1 · 判断方式", "小于或等于");
    expect(changed.mock.lastCall?.[0]).toEqual({ op: "all", args: [{ op: "lte", args: [{ value: 5 }, { value: 3 }] }, unchanged] });
    fireEvent.click(screen.getByRole("combobox", { name: "执行条件 · 判断方式" }));
    expect(screen.getAllByRole("option")).toHaveLength(10);
    expect(document.body.textContent).not.toMatch(/workflow\.input|nodes\.|"args"/);
  });
});
