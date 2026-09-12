import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { Field, FieldGroup } from "@/components/shared/form-field";
import { Card, CardHeader, CardTitle, CardContent, CardDescription } from "@/components/ui/card";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { usePlugins, usePlatformMutations } from "@/hooks/use-workflow-platform";
import { useUnsavedWork } from "@/hooks/use-unsaved-work";
import type { PluginRelease } from "@/lib/types/workflow-platform";
import { PluginHealth } from "./plugin-health";
import { RequestError } from "./feedback";
import { safePluginPageUrl } from "./plugin-links";
import { capabilityName, pluginName } from "./connection-model";

let installationDraft: { release: PluginRelease; fileName: string } | null = null;
function readInstallation(text: string): PluginRelease {
  const parsed = JSON.parse(text);
  const value = parsed?.release ?? parsed;
  if (!value || typeof value !== "object" || !Array.isArray(value.tools) || !value.configSchema || typeof value.configSchema !== "object" || Array.isArray(value.configSchema)
    || !["pluginId", "releaseId", "endpoint", "artifactDigest", "contractDigest", "protocolVersion"].every((key) => typeof value[key] === "string" && value[key])
    || !value.tools.every((tool: unknown) => tool && typeof tool === "object" && !Array.isArray(tool))) throw new Error();
  if (!safePluginPageUrl(value.endpoint)) throw new Error();
  return value as PluginRelease;
}
function Capabilities({ release }: { release: PluginRelease }) {
  return <section className="flex flex-col gap-2 text-sm" aria-label="提供的能力">
    <h3 className="font-medium">提供的能力</h3>
    <ul className="flex flex-col gap-2">{release.tools.map((tool, index) => <li key={index} className="flex flex-wrap items-center gap-2"><span>{capabilityName(tool, index)}</span><ResourceStatusBadge label={tool.effect === "write" ? "可保存或修改资料" : "只读取资料"} /></li>)}</ul>
  </section>;
}
export function PluginsPage() {
  const query = usePlugins();
  const mutations = usePlatformMutations();
  const [draft, setDraft] = useState(installationDraft);
  const [error, setError] = useState<unknown>(null);
  const [fileError, setFileError] = useState("");
  const [confirmed, setConfirmed] = useState(false);
  const [saved, setSaved] = useState(false);
  useUnsavedWork(Boolean(draft));
  async function selectFile(file?: File) {
    if (!file) return;
    setFileError(""); setSaved(false);
    try {
      const release = readInstallation(await file.text());
      installationDraft = { release, fileName: file.name };
      setDraft(installationDraft); setConfirmed(false);
    } catch { setFileError("无法读取这个安装文件。请选择服务提供方导出的完整连接文件；此前选择的内容仍会保留。"); }
  }
  async function register() {
    if (!draft || !confirmed) return;
    setError(null);
    try {
      await mutations.savePlugin.mutateAsync({ release: draft.release, enabled: false });
      installationDraft = null; setDraft(null); setConfirmed(false); setSaved(true);
    } catch (e) { setError(e); }
  }
  const existing = query.data?.items.some((item) => item.pluginId === draft?.release.pluginId);
  return <InventoryPageShell pageContext={{ title: "扩展服务", description: "添加独立服务，为任务提供读取和保存业务资料的能力" }}>
    <div className="flex flex-col gap-4">
      <RequestError error={query.error || error || mutations.enablePlugin.error} retry={() => void query.refetch()} />
      {query.isPending && <InventoryStatePanel title="正在读取扩展服务…" />}
      {query.data?.items.length === 0 && <InventoryStatePanel title="还没有扩展服务" description="使用服务提供方给你的安装文件添加服务，再选择启用。" />}
      {query.data?.items.map((plugin, index) => {
        const pageUrl = safePluginPageUrl(plugin.release.pageUrl);
        const name = pluginName(plugin.release);
        return <Card key={plugin.pluginId}>
          <CardHeader><CardTitle>{name}{name === "扩展服务" ? ` ${index + 1}` : ""}</CardTitle><CardDescription>{plugin.enabled ? "后续任务可以使用此服务。" : "尚未启用，任务暂时无法使用此服务。"}</CardDescription></CardHeader>
          <CardContent className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-2">
              <ResourceStatusBadge label={plugin.enabled ? "已启用" : "已停用"} />
              <Button variant="outline" disabled={mutations.enablePlugin.isPending} onClick={() => mutations.enablePlugin.mutate({ id: plugin.pluginId, enabled: !plugin.enabled })}>{plugin.enabled ? "停用" : "启用"} {name}</Button>
              {plugin.enabled && pageUrl && <Button asChild variant="outline"><a href={pageUrl} target="_blank" rel="noopener noreferrer">打开服务</a></Button>}
            </div>
            <Capabilities release={plugin.release} />
            <PluginHealth health={plugin.health} />
          </CardContent>
        </Card>;
      })}
      <Card>
        <CardHeader><CardTitle>添加或更新服务</CardTitle><CardDescription>选择服务提供方导出的安装文件，核对能力后添加。文件会自动处理，无需编写配置。</CardDescription></CardHeader>
        <CardContent><FieldGroup>
          <Field label="选择安装文件"><Input type="file" aria-label="选择安装文件" accept=".json,application/json" onChange={(event) => { void selectFile(event.target.files?.[0]); event.target.value = ""; }} /></Field>
          {fileError && <p role="alert" className="text-sm text-destructive">{fileError}</p>}
          {draft && <section className="flex flex-col gap-3 rounded-md border border-ui-separator p-3" aria-label="待添加的服务">
            <p className="font-medium">{pluginName(draft.release)}</p>
            <p className="text-sm">已读取 {draft.fileName}</p>
            <p className="break-all text-sm">服务所在地址：{new URL(draft.release.endpoint).origin}</p>
            <Capabilities release={draft.release} />
            {existing && <p className="text-sm">这会更新已有服务，并暂时停用它。已有任务保留原有设置；确认服务可用后可再次启用。</p>}
            <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={confirmed} onChange={(event) => setConfirmed(event.target.checked)} />我已核对服务来源和上述读取、保存能力</label>
            <div className="flex flex-wrap gap-2"><Button disabled={!confirmed || mutations.savePlugin.isPending} onClick={() => void register()}>{mutations.savePlugin.isPending ? "正在添加…" : existing ? "更新服务" : "添加服务"}</Button><Button variant="ghost" onClick={() => { installationDraft = null; setDraft(null); setConfirmed(false); }}>放弃本次选择</Button></div>
          </section>}
          {saved && <p role="status">已添加。确认服务可以使用后，点击上方“启用”。</p>}
        </FieldGroup></CardContent>
      </Card>
    </div>
  </InventoryPageShell>;
}
