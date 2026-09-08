import { FieldGroup, TextField } from "@/components/shared/form-field";
import { JsonObjectEditor } from "@/components/shared/json-object-editor";
import {
  parseDefinition,
  updateSource,
} from "@/lib/platform-authoring/package-source";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  AgentProperties,
  NodeProperties,
  WorkflowProperties,
} from "./package-properties";
export function PackageStructure({
  source,
  onChange,
  onDraftChange,
}: {
  source: string;
  onChange: (source: string) => void;
  onDraftChange?: (section: "agents" | "workflows", dirty: boolean) => void;
}) {
  const [selected, setSelected] = useState<string[]>([]);
  const [drafts, setDrafts] = useState<Record<string, boolean>>({});
  const pending = Object.values(drafts).some(Boolean);
  const propertyPending = Object.entries(drafts).some(
    ([key, dirty]) => key.startsWith("property:") && dirty,
  );
  const rawPending = !!drafts.agents || !!drafts.workflows;
  function track(id: string, dirty: boolean) {
    const next = { ...drafts, [id]: dirty };
    setDrafts(next);
    // Both sections block save whenever any unapplied property editor exists.
    onDraftChange?.("agents", Object.values(next).some(Boolean));
  }
  let definition;
  try {
    definition = parseDefinition(source);
  } catch (error) {
    return (
      <InventoryStatePanel
        tone="warning"
        title="Repair YAML to edit structure"
        description={error instanceof Error ? error.message : "Invalid source"}
      />
    );
  }
  const edit = (path: string[], value: unknown) =>
    onChange(updateSource(source, path, value));
  return (
    <FieldGroup>
      <TextField
        label="Package key"
        value={definition.metadata.key}
        onChange={(v) => edit(["metadata", "key"], v)}
      />
      <TextField
        label="Package name"
        value={definition.metadata.name}
        onChange={(v) => edit(["metadata", "name"], v)}
      />
      <TextField
        label="Description"
        value={definition.metadata.description ?? ""}
        onChange={(v) => edit(["metadata", "description"], v)}
      />
      <div className="grid min-w-0 gap-4 lg:grid-cols-[14rem_minmax(0,1fr)]">
        <nav
          aria-label="包内对象"
          className="flex max-h-96 flex-col gap-1 overflow-auto lg:sticky lg:top-0"
        >
          {Object.entries(definition.agents).map(([key]) => (
            <Button
              key={key}
              variant={
                selected.join(".") === `agents.${key}` ? "secondary" : "ghost"
              }
              disabled={pending}
              onClick={() => setSelected(["agents", key])}
            >
              Agent · {key}
            </Button>
          ))}
          {Object.entries(definition.workflows).map(([key, workflow]) => (
            <div key={key} className="flex flex-col gap-1">
              <Button
                variant={
                  selected.join(".") === `workflows.${key}`
                    ? "secondary"
                    : "ghost"
                }
                disabled={pending}
                onClick={() => setSelected(["workflows", key])}
              >
                Workflow · {key}
              </Button>
              {Object.keys(workflow?.nodes ?? {}).map((node) => (
                <Button
                  key={node}
                  variant={
                    selected.join(".") === `workflows.${key}.nodes.${node}`
                      ? "secondary"
                      : "ghost"
                  }
                  disabled={pending}
                  onClick={() => setSelected(["workflows", key, "nodes", node])}
                >
                  ↳ {node}
                </Button>
              ))}
            </div>
          ))}
        </nav>
        <fieldset disabled={rawPending} className="min-w-0">
          {selected.length === 0 && (
            <InventoryStatePanel
              title="选择对象编辑属性"
              description="属性修改写入同一 YAML；校验后查看依赖图。完整定义编辑可新增、删除或切换策略。"
            />
          )}
          {selected[0] === "agents" && definition.agents[selected[1]] && (
            <AgentProperties
              key={selected.join(".")}
              agent={definition.agents[selected[1]]}
              edit={(path, value) => edit([...selected, ...path], value)}
              draft={(id, dirty) => track(`property:${id}`, dirty)}
            />
          )}
          {selected[0] === "workflows" &&
            selected.length === 2 &&
            definition.workflows[selected[1]] && (
              <WorkflowProperties
                key={selected.join(".")}
                workflow={definition.workflows[selected[1]]}
                edit={(path, value) => edit([...selected, ...path], value)}
                draft={(id, dirty) => track(`property:${id}`, dirty)}
              />
            )}
          {selected.length === 4 &&
            definition.workflows[selected[1]]?.nodes?.[selected[3]] && (
              <NodeProperties
                key={selected.join(".")}
                node={definition.workflows[selected[1]].nodes[selected[3]]}
                edit={(path, value) => edit([...selected, ...path], value)}
                draft={(id, dirty) => track(`property:${id}`, dirty)}
              />
            )}
        </fieldset>
      </div>
      <fieldset
        disabled={propertyPending}
        className="flex min-w-0 flex-col gap-4"
      >
        <JsonObjectEditor
          label="Agent definitions"
          onDraftChange={(dirty) => track("agents", dirty)}
          value={definition.agents}
          onApply={(v) => edit(["agents"], v)}
        />
        <JsonObjectEditor
          label="Workflow definitions"
          onDraftChange={(dirty) => track("workflows", dirty)}
          value={definition.workflows}
          onApply={(v) => edit(["workflows"], v)}
        />
      </fieldset>
    </FieldGroup>
  );
}
