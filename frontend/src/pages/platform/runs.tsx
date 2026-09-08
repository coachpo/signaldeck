import { Link, useParams, useSearchParams } from "react-router";
import { CopyButton } from "@/components/shared/copy-button";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import {
  usePlatformRun,
  usePlatformMutations,
  isRunActive,
} from "@/hooks/use-workflow-platform";
import type { Json, RunDetail } from "@/lib/types/workflow-platform";
import { DependencyGraph } from "./dependency-graph";
import { ArtifactValue, EvidenceTree } from "./evidence";
import { findArtifacts } from "./artifact-references";
import { CacheProvenance } from "./cache-provenance";
import { RequestError } from "./feedback";
export { ResultHistoryPage as RunsPage } from "./result-history";
import { runSearch } from "./result-navigation";
import { ResultPage } from "./result-view";
export function RunPage() {
  const [search] = useSearchParams();
  return search.has("tab") ? <TechnicalRunPage /> : <ResultPage />;
}
function TechnicalRunPage() {
  const { runId } = useParams();
  const run = usePlatformRun(runId);
  if (run.isPending) return <InventoryStatePanel title="Loading run…" />;
  if (!run.data)
    return <RequestError error={run.error} retry={() => void run.refetch()} />;
  return <RunInspector key={run.data.id} run={run.data} />;
}
function RunInspector({ run }: { run: RunDetail }) {
  const [search, setSearch] = useSearchParams();
  const mutations = usePlatformMutations();
  const tabs = ["graph", "evidence", "artifacts", "snapshot"];
  const tab = tabs.includes(search.get("tab") ?? "")
    ? search.get("tab")!
    : "graph";
  const nodeTarget = search.get("node");
  const selected = run.evidence.find((e) =>
    search.get("target")
      ? e.id === search.get("target")
      : e.kind === "node" && e.nodeId === nodeTarget,
  );
  const awaitingNode =
    nodeTarget && run.spec.plan.nodeOrder.includes(nodeTarget) && !selected;
  const artifactEdges = run.evidence.flatMap((e) => [
    ...findArtifacts(e.output).map((a) => ({
      evidenceId: e.id,
      direction: "produced",
      ...a,
    })),
    ...findArtifacts(e.input).map((a) => ({
      evidenceId: e.id,
      direction: "consumed",
      ...a,
    })),
  ]);
  return (
    <WorkspacePageShell
      contextBar={
        <PageContextBar
          title={`Run ${run.id}`}
          description={`${run.packageKey} / ${run.workflowKey}`}
          status={<ResourceStatusBadge label={run.status} />}
          actions={
            <div className="flex flex-wrap gap-2">
              <CopyButton value={run.id} label="复制运行 ID" />
              <Button asChild variant="outline">
                <Link
                  to={{
                    pathname: `/runs/${encodeURIComponent(run.id)}`,
                    search: runSearch(search, {}).toString(),
                  }}
                >
                  返回结果
                </Link>
              </Button>
              {isRunActive(run) && (
                <Button
                  variant="outline"
                  disabled={
                    !!run.cancelRequestedAt || mutations.cancel.isPending
                  }
                  onClick={() =>
                    void mutations.cancel.mutateAsync(run.id).catch(() => {})
                  }
                >
                  Request cancellation
                </Button>
              )}
            </div>
          }
        />
      }
    >
      <div className="flex flex-col gap-4">
        <RequestError error={mutations.cancel.error || mutations.rerun.error} />
        {run.cancelRequestedAt && (
          <InventoryStatePanel
            title={
              isRunActive(run)
                ? "Cancellation requested — waiting for execution to stop"
                : run.status === "cancelled"
                  ? "Execution stopped"
                  : "Execution finished"
            }
            description="The status above is reported by the execution engine. External effects already performed are retained."
          />
        )}
        {run.errorCode && (
          <InventoryStatePanel tone="danger" title={run.errorCode} />
        )}
        <Tabs
          value={tab}
          onValueChange={(value) =>
            setSearch(runSearch(search, { tab: value }))
          }
        >
          <TabsList className="flex h-auto flex-wrap">
            <TabsTrigger value="graph">Run graph</TabsTrigger>
            <TabsTrigger value="evidence">Call evidence</TabsTrigger>
            <TabsTrigger value="artifacts">
              Dependency / artifact DAG
            </TabsTrigger>
            <TabsTrigger value="snapshot">Immutable snapshot</TabsTrigger>
          </TabsList>
          <TabsContent value="graph">
            <DependencyGraph
              plan={run.spec.plan}
              evidence={run.evidence}
              onSelect={(nodeId, evidenceId) =>
                setSearch(
                  runSearch(
                    search,
                    evidenceId
                      ? { tab: "evidence", target: evidenceId }
                      : { tab: "evidence", node: nodeId },
                  ),
                )
              }
            />
          </TabsContent>
          <TabsContent value="evidence">
            <div className="flex flex-col gap-4">
              <EvidenceTree evidence={run.evidence} selected={selected?.id} />
              {search.get("target") && !selected && (
                <InventoryStatePanel
                  tone="warning"
                  title="Evidence target does not exist in this run"
                />
              )}
              {nodeTarget && !run.spec.plan.nodeOrder.includes(nodeTarget) && (
                <InventoryStatePanel
                  tone="warning"
                  title="Node target does not exist in this run"
                />
              )}
              {awaitingNode && (
                <InventoryStatePanel
                  title={`Node ${nodeTarget}: no execution evidence`}
                  description="No input or output has been recorded for this node."
                />
              )}
              {selected && (
                <>
                  <h2 className="text-lg font-semibold">
                    {selected.kind} · {selected.nodeId}
                  </h2>
                  <p className="break-all text-sm">
                    ID {selected.id} · operation {selected.operationId ?? "—"} ·
                    attempt {selected.attempt}
                  </p>
                  <p className="text-sm">
                    Started {selected.startedAt ?? "—"} · finished{" "}
                    {selected.finishedAt ?? "—"}
                  </p>
                  {selected.errorCode && (
                    <InventoryStatePanel
                      tone="danger"
                      title={selected.errorCode}
                    />
                  )}
                  <ArtifactValue label="Input" value={selected.input} />
                  <ArtifactValue label="Output" value={selected.output} />
                  <CacheProvenance metadata={selected.metadata} />
                  <ArtifactValue label="Metadata" value={selected.metadata} />
                </>
              )}
            </div>
          </TabsContent>
          <TabsContent value="artifacts">
            <div className="flex flex-col gap-4">
              <DependencyGraph plan={run.spec.plan} evidence={run.evidence} />
              <ul
                aria-label="Artifact lineage edges"
                className="flex flex-col gap-2 text-sm"
              >
                {artifactEdges.map((edge) => (
                  <li
                    key={`${edge.evidenceId}:${edge.direction}:${edge.path}`}
                    className="break-all"
                  >
                    <Link
                      to={`?${runSearch(search, { tab: "evidence", target: edge.evidenceId })}`}
                    >
                      {edge.evidenceId}
                    </Link>{" "}
                    {edge.direction === "produced"
                      ? "produced →"
                      : "consumed ←"}{" "}
                    {edge.ref.digest} · {edge.path}
                  </li>
                ))}
              </ul>
              <ArtifactValue label="Run output" value={run.output} />
            </div>
          </TabsContent>
          <TabsContent value="snapshot">
            <ArtifactValue
              label="Frozen run specification"
              value={run.spec as unknown as Json}
            />
          </TabsContent>
        </Tabs>
      </div>
    </WorkspacePageShell>
  );
}
