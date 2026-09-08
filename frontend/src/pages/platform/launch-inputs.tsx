import { useMemo, useState } from "react";
import { SchemaValueEntryForm } from "@/components/platform-authoring/generated-form/schema-form";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import {
  createLaunchInputState,
  validateLaunchValueForSchema,
  createLaunchDraftFromPayload,
  createLaunchPayloadFromDraft,
  reconcileLaunchDraftChange,
} from "@/lib/platform-authoring/schema/launch-input-state";
import {
  isJsonObject,
  parseParameters,
} from "@/lib/platform-authoring/parameter-values";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
export function LaunchInputs({
  schema,
  value,
  onChange,
  onDirtyChange,
}: {
  schema: JsonObject;
  value: Json;
  onChange: (value: Json) => void;
  onDirtyChange: (dirty: boolean) => void;
}) {
  const state = useMemo(() => createLaunchInputState(schema), [schema]);
  const draft = isJsonObject(value)
    ? createLaunchDraftFromPayload(state, value)
    : null;
  const formSupported = state.schemaSupported && draft !== null;
  const [json, setJson] = useState<string | null>(null);
  const [error, setError] = useState("");
  function apply() {
    try {
      const next = parseParameters(json ?? JSON.stringify(value));
      const issues = validateLaunchValueForSchema(schema, next);
      if (issues.length)
        throw new Error(issues.map((i) => `${i.field}: ${i.issue}`).join("; "));
      onChange(next);
      setJson(null);
      onDirtyChange(false);
      setError("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Invalid input");
    }
  }
  return (
    <Tabs defaultValue={formSupported ? "form" : "json"}>
      <TabsList>
        <TabsTrigger value="form" disabled={!formSupported}>
          Input form
        </TabsTrigger>
        <TabsTrigger value="json">Advanced JSON</TabsTrigger>
      </TabsList>
      <TabsContent value="form">
        {state.schema && draft && (
          <SchemaValueEntryForm
            label="Workflow parameters"
            schema={state.schema}
            value={draft}
            onChange={(next) => {
              const updated = reconcileLaunchDraftChange(state, draft, next);
              onChange(createLaunchPayloadFromDraft(updated) as JsonObject);
              setJson(null);
              onDirtyChange(false);
            }}
          />
        )}
      </TabsContent>
      <TabsContent value="json">
        <div className="flex flex-col gap-3">
          {!formSupported && (
            <InventoryStatePanel
              title="Advanced JSON input"
              description="Use JSON for this root value or schema. The server validates the complete input contract at launch."
            />
          )}
          <Textarea
            aria-label="Parameters JSON"
            value={json ?? JSON.stringify(value, null, 2)}
            onChange={(e) => {
              setJson(e.target.value);
              onDirtyChange(true);
            }}
            spellCheck={false}
            className="min-h-40 font-mono"
          />
          {error && (
            <p role="alert" className="text-destructive">
              {error}
            </p>
          )}
          <Button variant="outline" onClick={apply}>
            Apply parameters JSON
          </Button>
          {json !== null && (
            <p className="text-sm text-muted-foreground">
              Apply this JSON before launching. The run uses the last applied
              value.
            </p>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}
