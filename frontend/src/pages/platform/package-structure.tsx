import { FieldGroup, TextField } from "@/components/shared/form-field";
import { JsonObjectEditor } from "@/components/shared/json-object-editor";
import {
  parseDefinition,
  updateSource,
} from "@/lib/platform-authoring/package-source";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
export function PackageStructure({
  source,
  onChange,
  onDraftChange,
}: {
  source: string;
  onChange: (source: string) => void;
  onDraftChange?: (section: "agents" | "workflows", dirty: boolean) => void;
}) {
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
      <JsonObjectEditor
        label="Agent definitions"
        onDraftChange={(dirty) => onDraftChange?.("agents", dirty)}
        value={definition.agents}
        onApply={(v) => edit(["agents"], v)}
      />
      <JsonObjectEditor
        label="Workflow definitions"
        onDraftChange={(dirty) => onDraftChange?.("workflows", dirty)}
        value={definition.workflows}
        onApply={(v) => edit(["workflows"], v)}
      />
    </FieldGroup>
  );
}
