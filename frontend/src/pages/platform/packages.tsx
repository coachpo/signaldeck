import { useEffect, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ConfirmDeleteDialog } from "@/components/shared/confirm-delete-dialog";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { usePackage, usePlatformMutations, usePlugins, useResources } from "@/hooks/use-workflow-platform";
import { useUnsavedWork } from "@/hooks/use-unsaved-work";
import { parseDefinition, updateSource } from "@/lib/platform-authoring/package-source";
import { authoringDiagnostic, newPackageSource, objectValue, stepLabels, workflowLabel } from "@/lib/platform-authoring/package-authoring";
import type { PackageDefinition, ValidationResult, WorkflowPackage } from "@/lib/types/workflow-platform";
import { DependencyGraph } from "./dependency-graph";
import { PackageStructure } from "./package-structure";
import type { AuthoringCatalog } from "./package-controls";
import { RequestError } from "./feedback";

// Drafts stay in this page session; browser persistent storage never receives workflow text.
const drafts = new Map<string, { source: string; savedSource: string; selection: string[]; tab: string }>();

export function PackageEditorPage() {
  const { packageId } = useParams();
  const query = usePackage(packageId);
  if (packageId && query.isPending) return <InventoryStatePanel title="正在读取工作流…" />;
  if (packageId && !query.data) return <RequestError error={query.error} retry={() => void query.refetch()} />;
  return <PackageEditor key={packageId ?? "new"} pkg={query.data} />;
}

function PackageEditor({ pkg }: { pkg?: WorkflowPackage }) {
  const draftKey = pkg?.key ?? "new";
  const [initial] = useState(() => drafts.get(draftKey) ?? { source: pkg?.source ?? newPackageSource(), savedSource: pkg?.source ?? "", selection: [], tab: "structure" });
  const [source, setSource] = useState(initial.source);
  const [savedSource, setSavedSource] = useState(initial.savedSource);
  const [selection, setSelection] = useState<string[]>(initial.selection);
  const [tab, setTab] = useState(initial.tab);
  const [validation, setValidation] = useState<{ source: string; result: ValidationResult } | null>(null);
  const [importError, setImportError] = useState("");
  const [replacement, setReplacement] = useState<string | null>(null);
  const importRef = useRef<HTMLInputElement>(null);
  const saveNavigation = useRef(false);
  const navigate = useNavigate();
  const mutations = usePlatformMutations();
  const resources = useResources();
  const plugins = usePlugins();
  const dirty = source !== savedSource;
  const blocker = useBlocker(() => dirty && !saveNavigation.current);
  useUnsavedWork(dirty);
  useEffect(() => {
    if (dirty) drafts.set(draftKey, { source, savedSource, selection, tab });
    else drafts.delete(draftKey);
  }, [dirty, draftKey, savedSource, selection, source, tab]);
  let definition: PackageDefinition | undefined;
  try { definition = parseDefinition(source); } catch { /* Import failures keep the current draft available for export. */ }
  const currentValidation = validation?.source === source ? validation.result : null;
  const plans = currentValidation?.plans ?? (source === pkg?.source ? pkg.plans : null);
  const catalog: AuthoringCatalog = {
    models: (resources.data?.items ?? []).filter((r) => r.kind === "model").map((r, index) => ({ value: r.resourceId, label: typeof r.config.name === "string" && r.config.name ? r.config.name : `AI 服务 ${index + 1}` })),
    connections: (resources.data?.items ?? []).filter((r) => r.kind === "tool").map((r, index) => ({ value: r.resourceId, label: typeof r.config.name === "string" && r.config.name ? r.config.name : `服务连接 ${index + 1}` })),
    tools: (plugins.data?.items ?? []).filter((plugin) => plugin.enabled).flatMap((plugin) => plugin.release.tools).map((tool, index) => {
      const inputSchema = objectValue(tool.inputSchema);
      return {
      value: typeof tool.toolId === "string" ? tool.toolId : "",
      label: typeof inputSchema?.title === "string" && inputSchema.title.trim() ? inputSchema.title : `${tool.effect === "read" ? "读取资料" : tool.effect === "write" ? "保存内容" : "服务操作"} ${index + 1}`,
      inputSchema, outputSchema: objectValue(tool.outputSchema), effect: typeof tool.effect === "string" ? tool.effect : undefined,
      resultLinks: Array.isArray(tool.resultLinks) ? tool.resultLinks.map((value, linkIndex) => {
        const link = objectValue(value);
        return { value: typeof link?.key === "string" ? link.key : "", label: typeof link?.label === "string" ? link.label : `查看结果 ${linkIndex + 1}` };
      }).filter((link) => link.value) : undefined,
      };
    }).filter((tool) => tool.value),
  };
  async function validate() {
    const result = await mutations.validate.mutateAsync(source);
    setValidation({ source, result });
  }
  async function save() {
    const result = await mutations.validate.mutateAsync(source);
    setValidation({ source, result });
    if (result.diagnostics.length || !result.definition || !result.plans) return;
    const saved = await mutations.savePackage.mutateAsync({ source, key: pkg?.key });
    setSource(saved.source); setSavedSource(saved.source); drafts.delete(draftKey);
    if (!pkg) { saveNavigation.current = true; navigate(`/workflow-packages/${encodeURIComponent(saved.key)}`); }
  }
  const busy = mutations.validate.isPending || mutations.savePackage.isPending;
  async function readImport(file: File) {
    setImportError("");
    try {
      const text = await file.text();
      const result = await mutations.validate.mutateAsync(text);
      if (result.diagnostics.length || !result.definition || !result.plans) {
        setImportError(`无法导入，当前草稿已保留。${result.diagnostics.map((item) => authoringDiagnostic(item, result.definition ?? undefined).message).filter((item, i, all) => all.indexOf(item) === i).join(" ")}`);
        return;
      }
      setReplacement(text);
    } catch { setImportError("无法读取或检查工作流文件。请检查文件和连接后重试，当前草稿已保留。"); }
  }
  return <WorkspacePageShell contextBar={<PageContextBar title={definition?.metadata.name || "制作工作流"} description={dirty ? "有未保存的更改 · 保存后才会用于新任务" : "工作流已保存"} actions={<div className="flex flex-wrap gap-2">
    <input ref={importRef} type="file" accept=".yaml,.yml,text/yaml,application/yaml" aria-label="选择导入文件" className="sr-only" disabled={busy} onChange={(e) => { const file = e.target.files?.[0]; if (file) void readImport(file); e.target.value = ""; }} />
    <Button variant="outline" disabled={busy} onClick={() => importRef.current?.click()}>导入工作流</Button>
    <Button variant="outline" title="保存后的导出保留设置与正文，不保留文件注释和原排版。" onClick={() => {
      const url = URL.createObjectURL(new Blob([source], { type: "application/yaml;charset=utf-8" }));
      const link = document.createElement("a"); link.href = url; link.download = `${definition?.metadata.name || "工作流"}.yaml`; link.click(); setTimeout(() => URL.revokeObjectURL(url), 0);
    }}>导出工作流</Button>
    <Button variant="outline" disabled={busy} onClick={() => void validate().catch(() => {})}>{mutations.validate.isPending ? "正在检查…" : "检查工作流"}</Button>
    <Button disabled={busy} onClick={() => void save().catch(() => {})}>{mutations.savePackage.isPending ? "正在保存…" : "保存工作流"}</Button>
    {pkg && <Button asChild variant="outline"><Link to={`/workflow-packages/${encodeURIComponent(pkg.key)}/run`}>开始任务</Link></Button>}
  </div>} />}>
    <div className="flex flex-col gap-4">
      <RequestError error={mutations.validate.error || mutations.savePackage.error} />
      <RequestError error={resources.error || plugins.error} retry={() => { void resources.refetch(); void plugins.refetch(); }} />
      {importError && <p role="alert" className="text-sm text-destructive">{importError}</p>}
      {pkg && savedSource && savedSource !== pkg.source && dirty && <InventoryStatePanel tone="warning" title="工作流已有更新" description="这里保留了你尚未保存的草稿。保存前请检查内容，避免覆盖其他页面中的更改。" />}
      {blocker.state === "blocked" && <InventoryStatePanel tone="warning" title="离开前保存工作流？" description="开始任务会使用上次保存的内容。可保留草稿并离开，在本次页面会话中返回继续；刷新或关闭页面前请先保存。" action={<><Button onClick={() => blocker.proceed()}>保留草稿并离开</Button><Button variant="outline" onClick={() => blocker.reset()}>继续编辑</Button></>} />}
      {currentValidation && <InventoryStatePanel tone={currentValidation.diagnostics.length ? "warning" : "neutral"} title={currentValidation.diagnostics.length ? "还有设置需要调整" : "检查通过，可以保存并开始任务"} description={currentValidation.diagnostics.map((item, index) => {
        const diagnostic = authoringDiagnostic(item, definition);
        return <div key={index} className="flex flex-col gap-1"><Button className="self-start" variant="link" onClick={() => { setTab("structure"); setSelection(diagnostic.selection); }}>{diagnostic.label}</Button><p>{diagnostic.message}</p></div>;
      })} />}
      <Tabs value={tab} onValueChange={setTab}>
        <TabsList><TabsTrigger value="structure">制作内容</TabsTrigger><TabsTrigger value="graph">步骤关系</TabsTrigger></TabsList>
        <TabsContent value="structure" forceMount className="data-[state=inactive]:hidden"><fieldset disabled={busy}><PackageStructure source={source} onChange={setSource} catalog={catalog} selected={selection} onSelect={setSelection} /></fieldset></TabsContent>
        <TabsContent value="graph">{plans && definition ? <div className="flex flex-col gap-4">{Object.values(plans).map((plan) => <DependencyGraph key={plan.workflowKey} plan={plan} name={workflowLabel(definition, plan.workflowKey)} nodeLabels={stepLabels(definition, plan.workflowKey)} onSelect={(key) => { setSelection(["workflows", plan.workflowKey, "nodes", key]); setTab("structure"); }} />)}</div> : <InventoryStatePanel title="检查工作流后查看步骤关系" description="每次修改步骤或信息来源后重新检查，就能看到最新的先后顺序。" action={<Button disabled={busy} onClick={() => void validate().catch(() => {})}>检查工作流</Button>} />}</TabsContent>
      </Tabs>
      <ConfirmDeleteDialog open={replacement !== null} title="用导入内容替换当前草稿？" description="当前尚未保存的更改将被替换。检查并保存后才会用于新任务；历史结果不变。保存后的导出保留设置与正文，不保留文件注释和原排版。" confirmLabel="替换当前草稿" onOpenChange={(open) => { if (!open) setReplacement(null); }} onConfirm={() => { if (replacement !== null) { setSource(pkg ? updateSource(replacement, ["metadata", "key"], pkg.key) : replacement); setSelection([]); setTab("structure"); setValidation(null); setReplacement(null); } }} />
    </div>
  </WorkspacePageShell>;
}
