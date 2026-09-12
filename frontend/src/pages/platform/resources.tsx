import { useState } from "react";
import { Button } from "@/components/ui/button";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { FieldGroup, ChoiceField } from "@/components/shared/form-field";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { useResources, usePlugins, usePlatformMutations } from "@/hooks/use-workflow-platform";
import type { Resource } from "@/lib/types/workflow-platform";
import { RequestError } from "./feedback";
import { ModelObservationDetails } from "./execution-diagnostic";
import { ConnectionConfigFields, ConnectionCredentials } from "./connection-config";
import { newConnectionConfig, prepareConnectionConfig } from "./connection-model";
import { useConnectionDraft } from "./use-connection-draft";
import { connectionName } from "./task-labels";

let selectedConnection: string | null = null;
export function ResourcesPage() {
  const query = useResources();
  const [editingId, setEditingId] = useState(selectedConnection);
  const [generation, setGeneration] = useState(0);
  const [savedName, setSavedName] = useState("");
  const editing = query.data?.items.find((item) => item.resourceId === editingId) ?? null;
  const choose = (id: string | null) => { selectedConnection = id; setEditingId(id); setGeneration((n) => n + 1); };
  return <InventoryPageShell pageContext={{ title: "服务连接", description: "管理模型和业务服务，决定任务使用的账户与范围", actions: <Button onClick={() => { setSavedName(""); choose(null); }}>添加连接</Button> }}>
    {savedName && <p role="status" className="mb-4 text-sm">已保存“{savedName}”。任务可以使用这项连接。</p>}
    <div className="grid min-w-0 gap-4 lg:grid-cols-2">
      <div className="flex flex-col gap-3">
        <RequestError error={query.error} retry={() => void query.refetch()} />
        {query.isPending && <InventoryStatePanel title="正在读取连接…" />}
        {query.data?.items.length === 0 && <InventoryStatePanel title="还没有服务连接" description="在右侧填写模型服务，或选择已经添加的业务服务。" />}
        {query.data?.items.map((resource) => {
          const name = connectionName(typeof resource.config.name === "string" ? resource.config.name : "", resource.resourceId);
          return <Card key={resource.resourceId}>
            <CardHeader><CardTitle>{name}</CardTitle><CardDescription>{resource.kind === "model" ? "模型服务" : "业务服务"}</CardDescription></CardHeader>
            <CardContent className="flex flex-wrap gap-3">
              <ResourceStatusBadge label={resource.hasCredentials ? "已保存密钥" : "未设置密钥"} />
              {resource.kind === "model" && <div className="w-full"><ModelObservationDetails observation={resource.modelObservation} /></div>}
              <Button variant="outline" onClick={() => choose(resource.resourceId)}>编辑 {name}</Button>
            </CardContent>
          </Card>;
        })}
      </div>
      {!editingId || editing ? <ResourceEditor key={`${editingId ?? "new"}:${generation}`} resource={editing} onSaved={(saved) => { setSavedName(String(saved.config.name ?? "服务连接")); choose(saved.resourceId); }} /> : <InventoryStatePanel title="正在读取所选连接…" />}
    </div>
  </InventoryPageShell>;
}

function ResourceEditor({ resource, onSaved }: { resource: Resource | null; onSaved: (resource: Resource) => void }) {
  const [id] = useState(resource?.resourceId ?? `connection-${crypto.randomUUID()}`);
  const draft = useConnectionDraft(resource?.resourceId ?? "new-resource", resource?.config ?? newConnectionConfig("model"));
  const [kind, setKind] = useState<"model" | "tool">(resource?.kind ?? (draft.config.pluginId !== undefined ? "tool" : "model"));
  const [error, setError] = useState<unknown>(null);
  const [validation, setValidation] = useState("");
  const [valid, setValid] = useState(true);
  const plugins = usePlugins();
  const { saveResource } = usePlatformMutations();
  async function save() {
    setError(null); setValidation("");
    let config;
    try { config = prepareConnectionConfig(kind, draft.config); }
    catch (e) { setValidation(e instanceof Error ? e.message : "请检查连接设置。"); return; }
    try {
      const credentials = Object.fromEntries(Object.entries(draft.credentials).filter(([, value]) => value !== ""));
      const saved = await saveResource.mutateAsync({ resourceId: id, kind, config, ...(Object.keys(credentials).length ? { credentials } : {}) });
      draft.saved(saved.config);
      onSaved(saved);
    } catch (e) { setError(e); }
  }
  return <Card>
    <CardHeader><CardTitle>{resource ? "编辑连接" : "添加连接"}</CardTitle><CardDescription>保存后可供任务使用。连接是否可用以实际执行结果为准。</CardDescription></CardHeader>
    <CardContent><FieldGroup>
      <RequestError error={error || plugins.error} />
      {validation && <p role="alert" className="text-sm text-destructive">{validation}</p>}
      {!resource && <ChoiceField label="连接用途" value={kind} options={[{ value: "model", label: "生成与分析内容" }, { value: "tool", label: "读取或保存业务资料" }]} onChange={(next) => {
        setKind(next as "model" | "tool"); setValid(true); setError(null);
        draft.update({ config: newConnectionConfig(next as "model" | "tool", String(draft.config.name ?? "")), credentials: {} });
      }} />}
      <ConnectionConfigFields kind={kind} value={draft.config} plugins={plugins.data?.items} onValidityChange={setValid} onChange={(config) => draft.update({ config, credentials: draft.credentials })} />
      <ConnectionCredentials kind={kind} values={draft.credentials} hasCredentials={resource?.hasCredentials} onChange={(credentials) => draft.update({ config: draft.config, credentials })} />
      {draft.dirty && <p className="text-sm text-muted-foreground">有尚未保存的修改。切换页面或模式会保留；刷新或关闭前请先保存。</p>}
      <Button disabled={saveResource.isPending || !valid} onClick={() => void save()}>{saveResource.isPending ? "正在保存…" : "保存连接"}</Button>
    </FieldGroup></CardContent>
  </Card>;
}
