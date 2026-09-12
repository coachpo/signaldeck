import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { WorkflowPresentation } from "@/lib/types/workflow-platform";
import type { MappingSource } from "@/lib/platform-authoring/mapping-sources";
import { PresentationEditor } from "./package-presentation";

const inputSources: MappingSource[] = [{ value: "workflow.input", label: "任务填写内容", schema: { type: "object", properties: {
  subject: { type: "string", title: "主题" }, question: { type: "string", title: "问题" },
} } }];
const outputSources: MappingSource[] = [{ value: "workflow.output", label: "最终结果", schema: { type: "string" } },
  { value: "nodes.create.output", label: "整理报告 · 完成内容", schema: { type: "object", properties: { id: { type: "string", title: "报告编号" } } } }];
const tools = [{ value: "acme/reports/create", label: "报告整理", sourceValues: ["nodes.create.output"], resultLinks: [{ value: "report", label: "阅读完整报告" }] }];

function select(label: string, option: string) {
  fireEvent.click(screen.getByRole("combobox", { name: label }));
  fireEvent.click(screen.getByRole("option", { name: option }));
}

function editPresentation(initial?: WorkflowPresentation) {
  const changed = vi.fn();
  function Editor() {
    const [value, setValue] = useState(initial);
    return <PresentationEditor value={value} inputSources={inputSources} outputSources={outputSources} tools={tools}
      onChange={(next) => { changed(next); setValue(next); }} />;
  }
  render(<Editor />);
  return changed;
}

describe("result reading editor", () => {
  it("does not materialize absent presentation settings before an explicit edit", () => {
    const changed = editPresentation();
    expect(changed).not.toHaveBeenCalled();
    select("结果名称", "使用固定名称");
    fireEvent.change(screen.getByLabelText("固定结果名称"), { target: { value: "研究结论" } });
    expect(changed.mock.lastCall?.[0]).toEqual({ version: "signaldeck.presentation/1", title: { kind: "static", text: "研究结论" } });
  });

  it("changes a title without rewriting placeholders, section declarations or omitted options", () => {
    const initial: WorkflowPresentation = {
      version: "signaldeck.presentation/1", title: { kind: "static", text: "原名称" },
      inputHints: [{ ref: "workflow.input.question", control: "textarea", placeholder: "保留用户自己的 JSON、代码和原文" }],
      sections: [{ kind: "notice", ref: "workflow.output", label: "需要留意", severity: "warning" }],
    };
    const changed = editPresentation(initial);
    fireEvent.change(screen.getByLabelText("固定结果名称"), { target: { value: "新名称" } });
    expect(changed.mock.lastCall?.[0]).toEqual({ ...initial, title: { kind: "static", text: "新名称" } });
    expect(screen.getByLabelText("填写提示 1 · 提示示例")).toHaveValue(initial.inputHints![0].placeholder);
    expect(document.body.textContent).not.toMatch(/signaldeck\.presentation|workflow\.input|workflow\.output|severity/);
  });

  it("creates distinct text hints and switches an input title through named fields", () => {
    const changed = editPresentation();
    fireEvent.click(screen.getByRole("button", { name: "添加填写提示" }));
    fireEvent.click(screen.getByRole("button", { name: "添加填写提示" }));
    expect(changed.mock.lastCall?.[0].inputHints).toEqual([
      { ref: "workflow.input.subject", control: "text" }, { ref: "workflow.input.question", control: "text" },
    ]);
    expect(screen.getByRole("button", { name: "添加填写提示" })).toBeDisabled();
    select("结果名称", "使用填写的信息");
    select("结果名称内容 · 内容 1", "问题");
    expect(changed.mock.lastCall?.[0].title).toEqual({ kind: "input", ref: "workflow.input.question" });
  });

  it("preserves unknown saved service links while another section changes", () => {
    const unknown = { kind: "link" as const, ref: "nodes.retired.output", label: "以前的报告", toolId: "acme/retired/report", linkKey: "original-page", required: true };
    const initial: WorkflowPresentation = { version: "signaldeck.presentation/1", sections: [unknown, { kind: "markdown", ref: "workflow.output", label: "正文" }] };
    const changed = editPresentation(initial);
    expect(screen.getByRole("combobox", { name: "结果分节 1 · 结果所属服务" })).toHaveTextContent("已保存的服务（当前不可用）");
    fireEvent.change(screen.getByLabelText("结果分节 2 · 标题"), { target: { value: "结论" } });
    expect(changed.mock.lastCall?.[0].sections).toEqual([unknown, { kind: "markdown", ref: "workflow.output", label: "结论" }]);
    expect(document.body.textContent).not.toMatch(/acme\/|nodes\.|original-page/);
  });

  it("builds a named service result link and offers every supported result section", () => {
    const changed = editPresentation();
    fireEvent.click(screen.getByRole("button", { name: "添加结果分节" }));
    fireEvent.click(screen.getByRole("combobox", { name: "结果分节 1 · 展示方式" }));
    expect(screen.getAllByRole("option")).toHaveLength(7);
    fireEvent.click(screen.getByRole("option", { name: "查看服务中的结果" }));
    expect(changed.mock.lastCall?.[0].sections).toEqual([{ kind: "link", ref: "nodes.create.output", label: "结果内容 1", toolId: "acme/reports/create", linkKey: "report" }]);
    expect(screen.getByRole("combobox", { name: "结果分节 1 · 结果所属服务" })).toHaveTextContent("报告整理");
    expect(screen.getByRole("combobox", { name: "结果分节 1 · 打开页面" })).toHaveTextContent("阅读完整报告");
    expect(document.body.textContent).not.toMatch(/acme\/|nodes\.|linkKey|toolId/);
  });
});
