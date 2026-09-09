import { useMemo, useState } from "react";
import { SchemaValueEntryForm, type InputHint } from "@/components/platform-authoring/generated-form/schema-form";
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
  inputHints,
  technical = true,
  value,
  onChange,
  onDirtyChange,
}: {
  schema: JsonObject;
  inputHints?: readonly InputHint[];
  technical?: boolean;
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
          {technical ? "Input form" : "填写输入"}
        </TabsTrigger>
        <TabsTrigger value="json">{technical ? "Advanced JSON" : "JSON 输入"}</TabsTrigger>
      </TabsList>
      <TabsContent value="form">
        {state.schema && draft && (
          <SchemaValueEntryForm
            label={technical ? "Workflow parameters" : "任务输入"}
            technical={technical}
            disabled={json !== null}
            inputHints={inputHints}
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
              title={technical ? "Advanced JSON input" : "使用 JSON 填写输入"}
              description={technical ? "Use JSON for this root value or schema. The server validates the complete input contract at launch." : "此任务需要使用 JSON 编辑完整输入。填写后先应用，再开始任务。"}
            />
          )}
          <Textarea
            aria-label={technical ? "Parameters JSON" : "任务输入 JSON"}
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
            {technical ? "Apply parameters JSON" : "应用 JSON 输入"}
          </Button>
          {json !== null && <Button variant="ghost" onClick={() => { setJson(null); setError(""); onDirtyChange(false); }}>{technical ? "Discard parameters JSON" : "放弃 JSON 修改"}</Button>}
          {json !== null && (
            <p className="text-sm text-muted-foreground">
              {technical ? "Apply this JSON before launching. The run uses the last applied value." : "请先应用或放弃当前 JSON 修改，再开始任务。"}
            </p>
          )}
        </div>
      </TabsContent>
    </Tabs>
  );
}
