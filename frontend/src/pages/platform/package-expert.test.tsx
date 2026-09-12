import { useState } from "react";
import { MemoryRouter } from "react-router";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PackageStructure } from "./package-structure";
import { DependencyGraph } from "./dependency-graph";
import { initialPackageSource, parseDefinition, updateSource } from "@/lib/platform-authoring/package-source";
import { authoringDiagnostic, hasStepReference, newPackageSource, stepRemovalBlockers } from "@/lib/platform-authoring/package-authoring";

function Editor({ initial = initialPackageSource }: { initial?: string }) {
  const [source, setSource] = useState("# retain author comment\n" + initial);
  return <MemoryRouter><PackageStructure source={source} onChange={setSource} catalog={{ models: [{ value: "default-model", label: "My AI" }], connections: [{ value: "approved-account", label: "My account" }], tools: [] }} /><output aria-label="source">{source}</output></MemoryRouter>;
}
const definition = () => parseDefinition(screen.getByLabelText("source").textContent!);
const choose = (label: string, name: string) => { fireEvent.click(screen.getByRole("combobox", { name: label })); fireEvent.click(screen.getByRole("option", { name })); };

describe("business workflow authoring", () => {
  it("edits prompt, services and limits without replacing mappings, annotations or comments", () => {
    const source = updateSource(initialPackageSource, ["agents", "assistant", "inputSchema"], { type: "null", "x-signaldeck-schema": "signaldeck.schema/2", default: null, examples: [null] });
    render(<Editor initial={source} />);
    fireEvent.click(screen.getByRole("button", { name: "Assistant" }));
    fireEvent.change(screen.getByLabelText("助手任务说明"), { target: { value: "Keep exact business input." } });
    fireEvent.change(screen.getByLabelText("总模型用量上限（模型计量单位）"), { target: { value: "9876" } });
    fireEvent.click(screen.getByRole("checkbox", { name: "My account" }));
    expect(definition().agents.assistant.budget?.maxTokens).toBe(9876);
    expect(definition().agents.assistant.resources).toEqual(["approved-account"]);
    expect(definition().agents.assistant.strategy).toMatchObject({ prompt: "Keep exact business input." });
    expect(definition().agents.assistant.inputSchema).toEqual(parseDefinition(source).agents.assistant.inputSchema);
    expect(definition().workflows).toEqual(parseDefinition(source).workflows);
    expect(screen.getByLabelText("source")).toHaveTextContent("# retain author comment");
    fireEvent.change(screen.getByLabelText("总模型用量上限（模型计量单位）"), { target: { value: "" } });
    expect(definition().agents.assistant.budget).not.toHaveProperty("maxTokens");
  });

  it("adds reusable assistants, workflows and steps using generated identities", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "添加助手" }));
    fireEvent.change(screen.getByLabelText("助手名称"), { target: { value: "校对助手" } });
    const assistantKey = Object.keys(definition().agents).find((key) => key !== "assistant")!;
    expect(assistantKey).toMatch(/^assistant-/);
    fireEvent.click(screen.getByRole("button", { name: "为Main添加步骤" }));
    choose("由谁完成", "校对助手");
    const step = Object.values(definition().workflows.main.nodes).find((node) => node.uses === assistantKey);
    expect(step?.inputMapping).toEqual({ ref: "workflow.input" });
    fireEvent.click(screen.getByRole("button", { name: "添加任务流程" }));
    fireEvent.change(screen.getByLabelText("任务流程名称"), { target: { value: "每周复核" } });
    expect(Object.values(definition().workflows).some((workflow) => workflow.name === "每周复核")).toBe(true);
    expect(screen.queryByLabelText("Package key")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Agent definitions")).not.toBeInTheDocument();
  });

  it("keeps an assistant in use and requires explicit confirmation before deleting an unused assistant", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "Assistant" }));
    fireEvent.click(screen.getByRole("button", { name: "移除助手" }));
    expect(screen.getByText(/仍有任务流程使用此助手/)).toBeVisible();
    expect(definition().agents.assistant).toBeDefined();
    fireEvent.click(screen.getByRole("button", { name: "添加助手" }));
    fireEvent.click(screen.getByRole("button", { name: "移除助手" }));
    expect(Object.keys(definition().agents)).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: "确认移除" }));
    expect(Object.keys(definition().agents)).toEqual(["assistant"]);
  });

  it("edits sources, dependencies, conditions and recovery with visible choices", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "为Main添加步骤" }));
    choose("交给助手的信息 · 来源", "步骤 1 · Assistant的结果");
    fireEvent.click(screen.getByRole("checkbox", { name: "步骤 1 · Assistant" }));
    fireEvent.click(screen.getByRole("button", { name: "设置执行条件" }));
    fireEvent.change(screen.getByLabelText("最多尝试次数（含首次）"), { target: { value: "3" } });
    const nodeKey = Object.keys(definition().workflows.main.nodes).find((key) => key !== "answer")!;
    expect(definition().workflows.main.nodes[nodeKey]).toMatchObject({ inputMapping: { ref: "nodes.answer.output" }, dependsOn: ["answer"], maxAttempts: 3, condition: { op: "exists", args: [{ ref: "workflow.input" }] } });
    fireEvent.click(screen.getByRole("button", { name: "移除执行条件" }));
    expect(definition().workflows.main.nodes[nodeKey]).not.toHaveProperty("condition");
  });

  it("retains imported comments and user instructions through source selection and repair", () => {
    const imported = "# Imported expert draft\n" + updateSource(initialPackageSource, ["agents", "assistant", "strategy", "prompt"], "Keep this code exactly:\n```js\nconst value = 0;\n```\n");
    let edited = updateSource(imported, ["metadata", "key"], "new-workflow");
    edited = updateSource(edited, ["workflows", "main", "nodes", "answer", "inputMapping"], { ref: "nodes.other.output" });
    edited = updateSource(edited, ["workflows", "main", "nodes", "answer", "inputMapping"], { ref: "workflow.input" });
    expect(edited).toContain("# Imported expert draft");
    expect(parseDefinition(edited).agents.assistant.strategy).toEqual(parseDefinition(imported).agents.assistant.strategy);
    expect(parseDefinition(edited).workflows).toEqual(parseDefinition(imported).workflows);
  });

  it("creates distinct new definitions and reports diagnostics without internal values", () => {
    expect(parseDefinition(newPackageSource()).metadata.key).not.toBe(parseDefinition(newPackageSource()).metadata.key);
    const diagnostic = authoringDiagnostic({ code: "dependency_cycle", path: "$.workflows.main.nodes.answer.inputMapping.ref", message: "internal trace", line: 30 }, parseDefinition(initialPackageSource));
    expect(diagnostic.selection).toEqual(["workflows", "main", "nodes", "answer"]);
    expect(diagnostic.label).toBe("Main · 步骤 1 · Assistant · 输入来源");
    expect(diagnostic.message).not.toMatch(/internal|nodes|ref/);
    expect(diagnostic.message).toContain("互相等待");
  });

  it("prevents deleting output sources but ignores literal text that happens to resemble a reference", () => {
    const workflow = parseDefinition(initialPackageSource).workflows.main;
    expect(stepRemovalBlockers(workflow, "answer", { answer: "回答" })).toEqual(["最终结果"]);
    expect(hasStepReference({ object: { value: { ref: "nodes.answer.output" } } }, "answer")).toBe(true);
    expect(hasStepReference({ value: { ref: "nodes.answer.output" } }, "answer")).toBe(false);
    expect(hasStepReference({ ref: "workflow.input", onMissing: { ref: "nodes.answer.output" } }, "answer")).toBe(true);
  });
});

describe("dependency viewport", () => {
  it("supports zoom, keyboard movement and named steps while explaining all dependencies", () => {
    render(<DependencyGraph plan={{ workflowKey: "hidden-main", nodeOrder: ["first", "last"], dependencies: { first: [], last: ["first"] }, edges: [{ source: "first", target: "last", sources: ["control", "input", "condition"], paths: ["nodes.last.condition"] }] }} nodeLabels={{ first: "阅读资料", last: "写出结论" }} />);
    fireEvent.click(screen.getByRole("button", { name: "放大图" }));
    expect(screen.getByLabelText("图缩放")).toHaveTextContent("125%");
    choose("定位步骤", "写出结论");
    expect(screen.getByRole("button", { name: "写出结论" })).toHaveFocus();
    const viewport = screen.getByRole("region", { name: "任务步骤" });
    const before = viewport.scrollLeft;
    fireEvent.keyDown(viewport, { key: "ArrowRight" });
    expect(viewport.scrollLeft).toBe(before + 60);
    for (const label of ["等待完成", "使用结果", "根据结果判断"]) expect(screen.getByText(label)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "自动布局 / 适合窗口" }));
    expect(viewport.scrollLeft).toBe(0);
    expect(screen.queryByText(/nodes\.last|hidden-main/)).not.toBeInTheDocument();
  });
});
