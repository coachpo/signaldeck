import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PackageStructure } from "./package-structure";
import { DependencyGraph } from "./dependency-graph";
import {
  initialPackageSource,
  parseDefinition,
  updateSource,
} from "@/lib/platform-authoring/package-source";

function Editor() {
  const [source, setSource] = useState(
    "# retain author comment\n" + initialPackageSource,
  );
  const [dirty, setDirty] = useState(false);
  return (
    <>
      <PackageStructure
        source={source}
        onChange={setSource}
        onDraftChange={(_, value) => setDirty(value)}
      />
      <output aria-label="source">{source}</output>
      <output aria-label="pending">{String(dirty)}</output>
    </>
  );
}
const definition = () =>
  parseDefinition(screen.getByLabelText("source").textContent!);

describe("expert properties and shared source", () => {
  it("edits presentation explicitly while preserving omission and schema annotations", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "Workflow · main" }));
    expect(definition().workflows.main).not.toHaveProperty("presentation");
    const presentation = { version: "signaldeck.presentation/1", title: { kind: "static", text: "A title" }, sections: [] };
    fireEvent.change(screen.getByLabelText("presentation"), { target: { value: JSON.stringify(presentation) } });
    expect(definition().workflows.main).not.toHaveProperty("presentation");
    expect(screen.getByLabelText("pending")).toHaveTextContent("true");
    fireEvent.click(screen.getByRole("button", { name: "Apply presentation" }));
    expect(definition().workflows.main.presentation).toEqual(presentation);
    const schema = { type: "null", "x-signaldeck-schema": "signaldeck.schema/2", default: null, examples: [null] };
    fireEvent.change(screen.getByLabelText("inputSchema"), { target: { value: JSON.stringify(schema) } });
    fireEvent.click(screen.getByRole("button", { name: "Apply inputSchema" }));
    fireEvent.change(screen.getByLabelText("Workflow name"), { target: { value: "Renamed" } });
    expect(definition().workflows.main.inputSchema).toEqual(schema);
    expect(definition().workflows.main.presentation).toEqual(presentation);
    fireEvent.click(screen.getByRole("button", { name: "移除 presentation" }));
    expect(definition().workflows.main).not.toHaveProperty("presentation");
    expect(definition().workflows.main.inputSchema).toEqual(schema);
  });
  it("edits prompt, grants and budget without replacing workflow mappings or comments", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "Agent · assistant" }));
    fireEvent.change(screen.getByLabelText("Prompt"), {
      target: { value: "Keep exact business input." },
    });
    fireEvent.change(screen.getByLabelText("maxTokens"), {
      target: { value: "9876" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加 resources" }));
    fireEvent.change(screen.getByLabelText("resources 1"), {
      target: { value: "approved-account" },
    });
    expect(definition().agents.assistant.budget?.maxTokens).toBe(9876);
    expect(definition().agents.assistant.resources).toEqual([
      "approved-account",
    ]);
    expect(definition().agents.assistant.strategy).toMatchObject({
      prompt: "Keep exact business input.",
    });
    expect(definition().workflows).toEqual(
      parseDefinition(initialPackageSource).workflows,
    );
    expect(screen.getByLabelText("source")).toHaveTextContent(
      "# retain author comment",
    );
    fireEvent.change(screen.getByLabelText("maxTokens"), {
      target: { value: "" },
    });
    expect(definition().agents.assistant.budget).not.toHaveProperty(
      "maxTokens",
    );
  });
  it("keeps invalid mapping drafts and blocks switching objects or raw replacement until discarded", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "↳ answer" }));
    fireEvent.change(screen.getByLabelText("inputMapping"), {
      target: { value: '{"ref":' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply inputMapping" }));
    expect(screen.getByRole("alert")).toBeVisible();
    expect(screen.getByLabelText("inputMapping")).toHaveValue('{"ref":');
    expect(
      screen.getByRole("button", { name: "Agent · assistant" }),
    ).toBeDisabled();
    expect(screen.getByLabelText("Agent definitions")).toBeDisabled();
    expect(screen.getByLabelText("pending")).toHaveTextContent("true");
    fireEvent.click(
      screen.getByRole("button", { name: "Discard inputMapping draft" }),
    );
    expect(screen.getByLabelText("pending")).toHaveTextContent("false");
    expect(
      screen.getByRole("button", { name: "Agent · assistant" }),
    ).toBeEnabled();
    expect(definition().workflows.main.nodes.answer.inputMapping).toEqual({
      ref: "workflow.input",
    });
  });
  it("applies node mappings and additional controls to the original YAML", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "↳ answer" }));
    fireEvent.change(screen.getByLabelText("inputMapping"), {
      target: { value: '{"ref":"nodes.first.output"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply inputMapping" }));
    fireEvent.click(screen.getByRole("button", { name: "添加 dependsOn" }));
    fireEvent.change(screen.getByLabelText("dependsOn 1"), {
      target: { value: "gate" },
    });
    expect(definition().workflows.main.nodes.answer).toMatchObject({
      inputMapping: { ref: "nodes.first.output" },
      dependsOn: ["gate"],
    });
    fireEvent.click(screen.getByRole("button", { name: "Workflow · main" }));
    fireEvent.change(screen.getByLabelText("maxParallelNodes"), {
      target: { value: "7" },
    });
    expect(definition().workflows.main.maxParallelNodes).toBe(7);
  });
  it("removes optional source values without adding null or disturbing other fields", () => {
    const source = updateSource(
      initialPackageSource,
      ["agents", "assistant", "budget"],
      { maxTokens: 5, maxToolCalls: 2 },
    );
    expect(
      parseDefinition(
        updateSource(
          source,
          ["agents", "assistant", "budget", "maxTokens"],
          undefined,
        ),
      ).agents.assistant.budget,
    ).toEqual({ maxToolCalls: 2 });
  });
});

describe("dependency viewport", () => {
  it("zooms, locates nodes, pans with the keyboard and retains merged edge provenance", () => {
    render(
      <DependencyGraph
        plan={{
          workflowKey: "main",
          nodeOrder: ["first", "last"],
          dependencies: { first: [], last: ["first"] },
          edges: [
            {
              source: "first",
              target: "last",
              sources: ["control", "input", "condition"],
              paths: ["nodes.last.condition"],
            },
          ],
        }}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "放大图" }));
    expect(screen.getByLabelText("图缩放")).toHaveTextContent("125%");
    fireEvent.click(screen.getByRole("combobox", { name: "定位节点" }));
    fireEvent.click(screen.getByRole("option", { name: "last" }));
    expect(screen.getByRole("button", { name: "last" })).toHaveFocus();
    const viewport = screen.getByRole("region", { name: "Workflow nodes" });
    const before = viewport.scrollLeft;
    fireEvent.keyDown(viewport, { key: "ArrowRight" });
    expect(viewport.scrollLeft).toBe(before + 60);
    for (const source of ["control", "input", "condition"])
      expect(screen.getByText(source)).toBeVisible();
    fireEvent.click(
      screen.getByRole("button", { name: "自动布局 / 适合窗口" }),
    );
    expect(viewport.scrollLeft).toBe(0);
    expect(screen.getByText("nodes.last.condition")).toBeVisible();
  });
});
