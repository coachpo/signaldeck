import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import {
  Field,
  FieldGroup,
  TextField,
  ChoiceField,
} from "@/components/shared/form-field";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardDescription,
} from "@/components/ui/card";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import {
  useResources,
  usePlatformMutations,
} from "@/hooks/use-workflow-platform";
import { parseObject } from "@/lib/platform-authoring/package-source";
import type { Resource } from "@/lib/types/workflow-platform";
import { RequestError } from "./feedback";
import { CopyButton } from "@/components/shared/copy-button";
const modelConfig = {
  name: "Local model",
  baseUrl: "http://localhost:11434/v1",
  modelId: "",
  apiStyle: "chat_completions",
  timeoutSeconds: 60,
};
const toolConfig = { name: "Tool resource", pluginId: "", scope: {} };
export function ResourcesPage() {
  const query = useResources();
  const [editing, setEditing] = useState<Resource | null>(null);
  const [generation, setGeneration] = useState(0);
  return (
    <InventoryPageShell
      pageContext={{
        title: "Resources",
        description: "Model connections and scoped tool resources",
        actions: (
          <Button
            onClick={() => {
              setEditing(null);
              setGeneration((n) => n + 1);
            }}
          >
            New resource
          </Button>
        ),
      }}
    >
      <div className="grid min-w-0 gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-3">
          <RequestError
            error={query.error}
            retry={() => void query.refetch()}
          />
          {query.isPending && (
            <InventoryStatePanel title="Loading resources…" />
          )}
          {query.data?.items.map((resource) => (
            <Card key={resource.resourceId}>
              <CardHeader>
                <CardTitle>{resource.resourceId}</CardTitle>
                <CardDescription>{resource.kind}</CardDescription>
              </CardHeader>
              <CardContent className="flex flex-wrap gap-2">
                <CopyButton
                  value={resource.resourceId}
                  text="复制资源 ID"
                  label={`复制资源 ID ${resource.resourceId}`}
                />
                <ResourceStatusBadge
                  label={
                    resource.hasCredentials
                      ? "Credentials configured"
                      : "No credentials"
                  }
                />
                <span className="break-all text-xs text-muted-foreground">
                  Credential revision {resource.credentialRevision}
                </span>
                <Button
                  variant="outline"
                  onClick={() => {
                    setEditing(resource);
                    setGeneration((n) => n + 1);
                  }}
                >
                  Edit {resource.resourceId}
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
        <ResourceEditor
          key={generation}
          resource={editing}
          onSaved={(saved) => {
            setEditing(saved);
            setGeneration((n) => n + 1);
          }}
        />
      </div>
    </InventoryPageShell>
  );
}
function ResourceEditor({
  resource,
  onSaved,
}: {
  resource: Resource | null;
  onSaved: (resource: Resource) => void;
}) {
  const [id, setId] = useState(resource?.resourceId ?? "");
  const [kind, setKind] = useState<"model" | "tool">(resource?.kind ?? "model");
  const [config, setConfig] = useState(
    JSON.stringify(resource?.config ?? modelConfig, null, 2),
  );
  const [credentials, setCredentials] = useState("");
  const [error, setError] = useState<unknown>(null);
  const { saveResource } = usePlatformMutations();
  async function save() {
    try {
      let privateValues: Record<string, string> | undefined;
      if (credentials.trim()) {
        try {
          const parsed = parseObject(credentials);
          if (Object.values(parsed).some((value) => typeof value !== "string"))
            throw new Error();
          privateValues = parsed as Record<string, string>;
        } catch {
          throw new Error(
            "New credentials must be a JSON object with string values.",
          );
        }
      }
      const saved = await saveResource.mutateAsync({
        resourceId: id,
        kind,
        config: parseObject(config),
        ...(privateValues ? { credentials: privateValues } : {}),
      });
      setCredentials("");
      onSaved(saved);
    } catch (e) {
      setError(e);
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{resource ? "Edit resource" : "New resource"}</CardTitle>
        <CardDescription>
          Saved credentials are write-only. Leave the credential field empty to
          retain them.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <FieldGroup>
          <RequestError error={error} />
          <TextField
            label="Resource ID"
            value={id}
            onChange={setId}
            disabled={!!resource}
          />
          <ChoiceField
            label="Resource kind"
            value={kind}
            disabled={!!resource}
            options={[
              { value: "model", label: "Model" },
              { value: "tool", label: "Tool" },
            ]}
            onChange={(value) => {
              const next = value as "model" | "tool";
              setKind(next);
              setConfig(
                JSON.stringify(
                  next === "model" ? modelConfig : toolConfig,
                  null,
                  2,
                ),
              );
            }}
          />
          <Field label="Resource configuration JSON">
            <Textarea
              aria-label="Resource configuration JSON"
              className="min-h-52 font-mono text-xs"
              value={config}
              onChange={(e) => setConfig(e.target.value)}
            />
          </Field>
          <Field
            label="New credentials JSON"
            description="Enter credential names and values. Values are encrypted and are never returned by reads."
          >
            <Textarea
              aria-label="New credentials JSON"
              autoComplete="off"
              value={credentials}
              onChange={(e) => setCredentials(e.target.value)}
              spellCheck={false}
            />
          </Field>
          <Button
            disabled={!id || saveResource.isPending}
            onClick={() => void save()}
          >
            Save resource
          </Button>
        </FieldGroup>
      </CardContent>
    </Card>
  );
}
