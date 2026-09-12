import { Link, useParams, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { usePlatformRun, usePlatformMutations, isRunActive } from "@/hooks/use-workflow-platform";
import { useRunResult } from "@/hooks/use-results";
import type { ExecutionEvidence, Json, RunDetail } from "@/lib/types/workflow-platform";
import { ArtifactValue, EvidenceTree } from "./evidence";
import { RequestError } from "./feedback";
import { runSearch } from "./result-navigation";
import { ResultPage } from "./result-view";
import { DeclaredResultSections } from "./result-sections";
import { ResultAttachmentView } from "./result-content";
import { ExecutionDiagnostic } from "./execution-diagnostic";
import { ModelBudgetSummary } from "./model-usage-panel";
import { ResultFreshness } from "./result-freshness";
import { evidenceName, frozenTool, objectValue, recordedTime, runSources, runWorkflow, stepName, toolName } from "./result-context";
import { resultStatusLabels, resultStatusTone } from "./result-labels";
import { ConnectionSummary } from "./task-preparation";
import { artifactPresentation } from "./result-artifact-presentation";
import { findArtifacts } from "./artifact-references";
import { CacheProvenance } from "./cache-provenance";
import { RecordedCondition, RecordedMapping } from "./result-rules";
import { ResultInputSources } from "./result-input-sources";
import type { ResultSection } from "@/lib/types/result";
export { ResultHistoryPage as RunsPage } from "./result-history";

export function RunPage() {
  const [search] = useSearchParams();
  return search.has("tab") ? <ExecutionPage /> : <ResultPage />;
}
function ExecutionPage() {
  const { runId } = useParams();
  const run = usePlatformRun(runId);
  if (run.isPending) return <InventoryStatePanel title="正在读取执行过程…" />;
  if (!run.data) return <RequestError error={run.error} retry={() => void run.refetch()} />;
  return <RunInspector key={run.data.id} run={run.data} />;
}
function RunInspector({ run }: { run: RunDetail }) {
  const [search, setSearch] = useSearchParams();
  const result = useRunResult(run.id);
  const mutations = usePlatformMutations();
  const workflow = runWorkflow(run);
  const tab = ["graph", "evidence", "artifacts", "snapshot"].includes(search.get("tab") ?? "") ? search.get("tab")! : "graph";
  const nodeTarget = search.get("node");
  const operationTarget = search.get("operation");
  const selected = run.evidence.find((item) => search.get("target") ? item.id === search.get("target") : operationTarget ? item.kind === "tool" && item.operationId === operationTarget : nodeTarget ? item.kind === "node" && item.nodeId === nodeTarget : item.kind === "node");
  const awaitingNode = nodeTarget && run.spec.plan.nodeOrder.includes(nodeTarget) && !selected;
  return <WorkspacePageShell contextBar={<PageContextBar
    title={workflow?.name || run.spec.definition.metadata.name || "任务执行过程"}
    description={`执行过程 · ${recordedTime(run.createdAt)}`}
    status={<ResourceStatusBadge tone={resultStatusTone(run.status)} label={resultStatusLabels[run.status] ?? "状态待确认"} />}
    actions={<div className="flex flex-wrap gap-2">
      <Button asChild variant="outline"><Link to={{ pathname: `/runs/${encodeURIComponent(run.id)}`, search: runSearch(search, {}).toString() }}>返回结果</Link></Button>
      {isRunActive(run) && <Button variant="outline" disabled={!!run.cancelRequestedAt || mutations.cancel.isPending} onClick={() => void mutations.cancel.mutateAsync(run.id).catch(() => {})}>取消本次运行</Button>}
    </div>}
  />}>
    <div className="flex flex-col gap-4">
      <RequestError error={mutations.cancel.error} />
      {run.cancelRequestedAt && <InventoryStatePanel title={isRunActive(run) ? "已请求取消，正在等待执行停止" : run.status === "cancelled" ? "本次运行已取消" : "执行已结束"} description="已完成的保存或其他外部操作仍会保留。" />}
      {run.hasUnknownResults && <InventoryStatePanel tone="warning" title="读取结果未确认" description="服务尚未返回确定的读取结果。可以查看下方步骤或重新读取，此操作不涉及保存。" />}
      {run.hasUnknownEffects && <InventoryStatePanel tone="warning" title="保存状态待核实" description="服务尚未确认是否保存成功。请先核对目标位置与下方操作记录，避免重复保存。" />}
      {run.errorCode && run.status !== "cancelled" && (result.isPending ? <p role="status">正在读取失败原因…</p> : <ExecutionDiagnostic code={result.data?.errorCode ?? run.errorCode} category={result.data?.errorCategory} />)}
      <Tabs value={tab} onValueChange={(value) => setSearch(runSearch(search, { tab: value }))}>
        <TabsList className="flex h-auto flex-wrap">
          <TabsTrigger value="graph">步骤进度</TabsTrigger>
          <TabsTrigger value="evidence">执行过程</TabsTrigger>
          <TabsTrigger value="artifacts">资料与附件</TabsTrigger>
          <TabsTrigger value="snapshot">本次设置</TabsTrigger>
        </TabsList>
        <TabsContent value="graph"><ExecutionSteps run={run} onSelect={(node, target) => setSearch(runSearch(search, target ? { tab: "evidence", target } : { tab: "evidence", node }))} /></TabsContent>
        <TabsContent value="evidence">
          <div className="flex flex-col gap-4">
            <EvidenceTree evidence={run.evidence} selected={selected?.id} run={run} />
            {(search.get("target") || operationTarget) && !selected && <InventoryStatePanel tone="warning" title="本次任务中找不到所选操作" description="请从上方选择其他步骤，或返回结果查看当前状态。" />}
            {nodeTarget && !run.spec.plan.nodeOrder.includes(nodeTarget) && <InventoryStatePanel tone="warning" title="本次任务中没有这个步骤" />}
            {awaitingNode && <InventoryStatePanel title={`${stepName(run, nodeTarget)}：尚未开始处理`} description="目前尚未记录此步骤的输入或结果。可返回步骤进度查看前置工作。" />}
            {selected && <EvidenceDetails run={run} item={selected} sections={result.data?.sections} />}
            <RequestError error={result.error} retry={() => void result.refetch()} />
            {selected && !!result.data?.sections?.filter((section) => section.nodeId === selected.nodeId).length && <section className="flex flex-col gap-3" aria-label="此步骤已确认的内容">
              <h2 className="font-semibold">此步骤已确认的内容</h2>
              <DeclaredResultSections sections={result.data.sections.filter((section) => section.nodeId === selected.nodeId)} search={search} run={run} />
            </section>}
          </div>
        </TabsContent>
        <TabsContent value="artifacts"><div className="flex flex-col gap-4">
          <RequestError error={result.error} retry={() => void result.refetch()} />
          {result.isPending && <p>正在读取资料与附件…</p>}
          {result.data?.freshness?.map((value, index) => <ResultFreshness key={index} value={value} />)}
          <ul>{result.data?.attachments?.map((attachment, index) => <ResultAttachmentView key={index} attachment={attachment} presentation={artifactPresentation(run, attachment, findArtifacts(attachment.reference)[0]?.ref.digest ?? "")} />)}</ul>
          {result.data && !result.data.attachments?.length && <InventoryStatePanel title="本次没有单独的附件" description="已确认的正文与保存入口可在结果页阅读。" />}
          <Button asChild variant="outline"><Link to={{ pathname: `/runs/${encodeURIComponent(run.id)}`, search: runSearch(search, {}).toString() }}>阅读已确认结果</Link></Button>
        </div></TabsContent>
        <TabsContent value="snapshot"><RunSettings run={run} /></TabsContent>
      </Tabs>
    </div>
  </WorkspacePageShell>;
}
function ExecutionSteps({ run, onSelect }: { run: RunDetail; onSelect: (node: string, target?: string) => void }) {
  return <ol aria-label="任务步骤" className="flex flex-col gap-3">
    {run.spec.plan.nodeOrder.map((nodeId, index) => {
      const attempts = run.evidence.filter((item) => item.kind === "node" && item.nodeId === nodeId).sort((a, b) => b.attempt - a.attempt);
      const latest = attempts[0];
      const dependencies = run.spec.plan.dependencies[nodeId] ?? [];
      return <li key={nodeId} className="flex flex-col gap-2 rounded border border-border bg-card p-4">
        <div className="flex flex-wrap items-center gap-2"><span className="text-sm text-muted-foreground">{index + 1}</span><Button variant="outline" onClick={() => onSelect(nodeId, latest?.id)}>{stepName(run, nodeId)}</Button><ResourceStatusBadge tone={resultStatusTone(latest?.status)} label={latest ? latest.status === "unknown" ? "结果未确认" : resultStatusLabels[latest.status] ?? "等待开始" : "尚未开始"} /></div>
        <p className="text-sm text-muted-foreground">{dependencies.length ? `前置步骤：${dependencies.map((id) => stepName(run, id)).join("、")}` : "无需等待其他步骤"}</p>
        {latest && <p className="text-sm">开始：{recordedTime(latest.startedAt)} · 完成：{recordedTime(latest.finishedAt)} · 已尝试 {latest.attempt} 次</p>}
      </li>;
    })}
  </ol>;
}
function EvidenceDetails({ run, item, sections }: { run: RunDetail; item: ExecutionEvidence; sections?: ResultSection[] }) {
  const tool = frozenTool(run, item.toolId);
  return <section className="flex min-w-0 flex-col gap-3 rounded border border-border bg-card p-4" aria-label="所选操作详情">
    <h2 className="font-semibold">{evidenceName(item, run)}</h2>
    <p className="text-sm">第 {item.attempt} 次 · {item.status === "unknown" ? "结果未确认" : resultStatusLabels[item.status] ?? "等待开始"}</p>
    <p className="text-sm">开始：{recordedTime(item.startedAt)} · 完成：{recordedTime(item.finishedAt)}</p>
    {tool && <p className="text-sm">操作权限：{tool.effect === "read" ? "只读取资料" : tool.effect === "write" ? "可以保存或更改资料" : "历史记录未明确，请核对目标位置"}</p>}
    {item.status === "unknown" && <p className="text-sm">{tool?.effect === "read" || item.kind === "model" ? "这次读取或生成尚未得到确认，可以重新获取；不表示已保存内容。" : "尚未确认是否产生了外部更改。请核对目标位置后再决定是否重试。"}</p>}
    {item.errorCode && (item.status === "failed" || item.status === "timed_out") && <ExecutionDiagnostic code={item.errorCode} />}
    <ResultInputSources run={run} item={item} sections={sections} />
    <CacheProvenance metadata={item.metadata} />
  </section>;
}
function RunSettings({ run }: { run: RunDetail }) {
  const workflow = runWorkflow(run);
  return <div className="flex min-w-0 flex-col gap-4">
    <p className="text-sm">这里保留开始本次任务时确认的输入和限制，之后修改任务不会改变本次记录。</p>
    <ArtifactValue label="本次输入" value={run.spec.parameters} schema={workflow?.inputSchema} />
    <section className="flex flex-col gap-2 text-sm"><h2 className="font-semibold">执行限制</h2>
      <p>最长执行时间：{workflow?.deadlineSeconds ? `${workflow.deadlineSeconds} 秒` : "沿用任务默认限制"}</p>
      <p>最多同时处理：{workflow?.maxParallelNodes ?? 8} 个步骤</p>
      <p>某步失败后：{workflow?.failurePolicy === "fail_fast" ? "停止后续步骤" : "继续不受影响的步骤"}</p>
    </section>
    <ModelBudgetSummary settings={run.spec.definition as unknown as Json} />
    {workflow && <section className="flex flex-col gap-2 text-sm"><h2 className="font-semibold">最终结果来源</h2><RecordedMapping value={workflow.outputMapping} targetSchema={workflow.outputSchema} sources={runSources(run)} /></section>}
    <section className="flex flex-col gap-3"><h2 className="font-semibold">本次使用的服务</h2>
      {[...Object.values(run.spec.modelBindings), ...Object.values(run.spec.resourceBindings)].map(objectValue).filter((config) => !!config).map((config, index) => <div key={index} className="flex flex-col gap-2 rounded bg-ui-surface-grouped p-3 text-sm">
        <h3 className="font-medium">{typeof config.name === "string" && config.name ? config.name : `服务连接 ${index + 1}`}</h3>
        <ConnectionSummary config={config} />
      </div>)}
    </section>
    <section className="flex flex-col gap-3"><h2 className="font-semibold">各步骤的工作要求与权限</h2>
      {run.spec.plan.nodeOrder.map((id) => {
        const node = workflow?.nodes[id];
        const agent = node && run.spec.definition.agents[node.uses];
        if (!agent) return null;
        return <div key={id} className="flex flex-col gap-2 rounded bg-ui-surface-grouped p-3 text-sm"><h3 className="font-medium">{stepName(run, id)}</h3>
          {agent.strategy.kind === "model" && <p className="whitespace-pre-wrap break-words">{agent.strategy.prompt}</p>}
          <p>最多尝试：{node?.maxAttempts ?? 1} 次</p>
          {agent.budget && <p>最多使用服务 {agent.budget.maxToolCalls ?? "未记录"} 次；同时处理上限 {agent.budget.maxParallelTools ?? "未记录"} 次；最长处理 {agent.budget.deadlineSeconds ?? "未记录"} 秒。</p>}
          {node && <div className="flex flex-col gap-2"><h4 className="font-medium">输入来源</h4><RecordedMapping value={node.inputMapping} targetSchema={agent.inputSchema} sources={runSources(run, id)} /></div>}
          {node?.condition && <div className="flex flex-col gap-2"><h4 className="font-medium">开始条件</h4><RecordedCondition value={node.condition} sources={runSources(run, id)} /><p>不满足时，此步骤会标记为已跳过。</p></div>}
          {!!node?.acceptUpstreamStates?.length && <p>可接受的前置步骤状态：{node.acceptUpstreamStates.map((status) => status === "unknown" ? "结果未确认" : resultStatusLabels[status] ?? "结果未确认").join("、")}</p>}
          <ul>{(agent.tools ?? []).map((toolId, index) => { const tool = frozenTool(run, toolId); return <li key={toolId}>{toolName(run, toolId, index + 1)} · {tool?.effect === "read" ? "只读" : tool?.effect === "write" ? "允许更改资料" : "权限未记录"}</li>; })}</ul>
        </div>;
      })}
    </section>
  </div>;
}
