import { Checkbox } from "@/components/ui/checkbox";
import { useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { ChoiceField } from "@/components/shared/form-field";
import { usePlatformMutations, usePlugins, useResources } from "@/hooks/use-workflow-platform";
import { useConnectionPresets } from "@/hooks/use-task-experience";
import { RequestError } from "./feedback";
import { ModelObservationDetails } from "./execution-diagnostic";
import { connectionName } from "./task-labels";
import { ConnectionConfigFields, ConnectionCredentials } from "./connection-config";
import { newConnectionConfig, prepareConnectionConfig, pluginName } from "./connection-model";
import { useConnectionDraft } from "./use-connection-draft";
import type { ConnectionPreset, Requirement } from "@/lib/types/task-experience";
import type { Plugin, Resource } from "@/lib/types/workflow-platform";

export function TaskConnections({ requirements, onSaved }: { requirements: Requirement[]; onSaved: () => void }) {
  const presets = useConnectionPresets();
  const resources = useResources();
  const plugins = usePlugins();
  return <section className="flex flex-col gap-3" aria-label="就地连接">
    <h2 className="font-medium">连接与保存位置</h2>
    <p className="text-sm text-muted-foreground">选择已提供的连接或填写自己的服务。保存后会重新检查任务所需设置。</p>
    <RequestError error={presets.error || resources.error || plugins.error} retry={() => { void presets.refetch(); void resources.refetch(); void plugins.refetch(); }} />
    {requirements.filter((r) => r.kind !== "plugin").map((r) => <ConnectionEditor key={r.id} requirement={r}
      presets={presets.data?.items.filter((p) => p.resourceId === r.id && p.kind === r.kind) ?? []}
      resources={resources.data?.items.filter((item) => item.kind === r.kind && item.resourceId !== r.id) ?? []}
      plugins={plugins.data?.items ?? []}
      presetsPending={presets.isPending} presetsFailed={Boolean(presets.error)} onSaved={onSaved} />)}
    {requirements.filter((r) => r.kind === "plugin" && !r.configured).map((r) => {
      const plugin = plugins.data?.items.find((item) => item.pluginId === r.id);
      return <div key={r.id} className="flex flex-col gap-2">
        <p>{plugin ? pluginName(plugin.release) : "任务需要的扩展服务"}尚未添加或启用。请先完成服务设置，再回来继续。</p>
        <Button variant="outline" asChild><Link to="/plugins">设置扩展服务</Link></Button>
      </div>;
    })}
  </section>;
}

function ConnectionEditor({ requirement, presets, resources, plugins, presetsPending, presetsFailed, onSaved }: {
  requirement: Requirement; presets: ConnectionPreset[]; resources: Resource[]; plugins: Plugin[];
  presetsPending: boolean; presetsFailed: boolean; onSaved: () => void;
}) {
  const { saveResource } = usePlatformMutations();
  const kind = requirement.kind === "model" ? "model" : "tool";
  const name = requirement.name && requirement.name !== requirement.id ? requirement.name : kind === "model" ? "模型服务" : "业务服务";
  const draft = useConnectionDraft(`task:${requirement.id}`, requirement.configured ? { ...requirement.config, name: requirement.config.name || name } : newConnectionConfig(kind, name));
  const [selected, setSelected] = useState(requirement.configured ? "current" : "");
  const [confirmed, setConfirmed] = useState(false);
  const [valid, setValid] = useState(true);
  const [error, setError] = useState<unknown>(null);
  const [validation, setValidation] = useState("");
  const [saved, setSaved] = useState(false);
  const preset = presets.find((p) => p.id === selected);
  const fields = preset?.credentialFields ?? [];
  const showForm = requirement.configured || Boolean(selected) || draft.dirty || (!presetsPending && !presets.length);
  async function save() {
    if (!confirmed) return;
    setError(null); setValidation(""); setSaved(false);
    let config;
    try { config = prepareConnectionConfig(kind, draft.config); }
    catch (e) { setValidation(e instanceof Error ? e.message : "请检查连接设置。"); return; }
    const entered = Object.fromEntries(Object.entries(draft.credentials).filter(([, value]) => value !== ""));
    try {
      await saveResource.mutateAsync({ resourceId: requirement.id, kind, config, ...(Object.keys(entered).length ? { credentials: entered } : {}) });
      draft.saved(config); setSaved(true); onSaved();
    } catch (e) { setError(e); }
  }
  return <details className="rounded-md border border-ui-separator p-3" open={!requirement.configured || undefined}>
    <summary className="cursor-pointer font-medium">{name} · {requirement.configured ? "管理连接" : "补齐连接"}</summary>
    <div className="flex flex-col gap-3 pt-3">
      {kind === "model" && requirement.configured && <ModelObservationDetails observation={requirement.modelObservation} />}
      <RequestError error={error} />
      {validation && <p role="alert" className="text-sm text-destructive">{validation}</p>}
      {presetsPending && <p role="status">正在查找可用连接…</p>}
      {presetsFailed && <p role="status">暂时无法更新连接选项。可以重试，或继续填写服务地址；当前输入会保留。</p>}
      <ChoiceField label="连接来源" value={selected || (showForm ? "custom" : "")} options={[
        ...(requirement.configured ? [{ value: "current", label: "使用当前连接" }] : []),
        ...presets.map((p) => ({ value: p.id, label: p.name })),
        ...resources.map((r, index) => ({ value: `saved:${r.resourceId}`, label: `复制 ${connectionName(String(r.config.name ?? ""), r.resourceId)} 的设置${r.config.name ? "" : ` ${index + 1}`}` })),
        { value: "custom", label: "填写自己的服务" },
      ]} onChange={(next) => {
        setSelected(next); setConfirmed(false); setSaved(false); setError(null); setValidation(""); setValid(true);
        const chosen = presets.find((p) => p.id === next);
        const copied = resources.find((r) => `saved:${r.resourceId}` === next);
        const config = chosen ? { ...chosen.config, name: chosen.config.name || chosen.name } : copied ? copied.config : next === "current" ? { ...requirement.config, name: requirement.config.name || name } : newConnectionConfig(kind, name);
        draft.update({ config, credentials: {} });
      }} />
      {!showForm && !presetsPending && <p role="status">请选择一个连接，或填写自己的服务。</p>}
      {selected.startsWith("saved:") && <p className="text-sm text-muted-foreground">已复制服务设置。密钥不会从其他连接复制，需要时请在下方填写。</p>}
      {showForm && <>
        <ConnectionConfigFields kind={kind} value={draft.config} plugins={plugins} onValidityChange={setValid} onChange={(config) => { draft.update({ config, credentials: draft.credentials }); setConfirmed(false); setSaved(false); }} />
        <ConnectionCredentials kind={kind} values={draft.credentials} fields={fields} hasCredentials={requirement.hasCredentials} onChange={(credentials) => { draft.update({ config: draft.config, credentials }); setSaved(false); }} />
        <label className="flex items-center gap-2 text-sm"><Checkbox checked={confirmed} onCheckedChange={(checked) => setConfirmed(checked === true)} />确认使用以上服务、账户、业务范围及保存位置</label>
        <Button variant="outline" onClick={() => void save()} disabled={saveResource.isPending || !confirmed || !valid || fields.some((field) => field.required && !draft.credentials[field.key] && !requirement.hasCredentials)}>{saveResource.isPending ? "正在保存…" : "保存连接"}</Button>
        {saved && <p role="status">已保存。任务准备已重新检查；服务是否可用仍需实际执行确认。</p>}
        {draft.dirty && <p className="text-sm text-muted-foreground">请在刷新或关闭页面前保存连接。密钥不会写入浏览器存储。</p>}
      </>}
    </div>
  </details>;
}
