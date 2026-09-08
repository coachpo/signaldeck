import { Link, useNavigate, useParams, useSearchParams } from "react-router";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";
import {
  usePlatformRuns,
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
export function RunsPage() {
  const runs = usePlatformRuns();
  return (
    <InventoryPageShell
      pageContext={{
        title: "Runs",
        description: "Durable execution and retained evidence",
        actions: (
          <Button variant="outline" onClick={() => void runs.refetch()}>
            Refresh runs
          </Button>
        ),
      }}
    >
      <RequestError error={runs.error} retry={() => void runs.refetch()} />
      {runs.isPending ? (
        <InventoryStatePanel title="Loading runs…" />
      ) : runs.data?.items.length ? (
        <ResourceTableFrame>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Run</TableHead>
                <TableHead>Workflow</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Origin</TableHead>
                <TableHead>Created</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data.items.map((run) => (
                <TableRow key={run.id}>
                  <TableCell>
                    <Button asChild variant="link">
                      <Link to={`/runs/${encodeURIComponent(run.id)}`}>
                        {run.id}
                      </Link>
                    </Button>
                  </TableCell>
                  <TableCell>
                    {run.packageKey} / {run.workflowKey}
                  </TableCell>
                  <TableCell>
                    <ResourceStatusBadge label={run.status} />
                    {run.cancelRequestedAt && isRunActive(run) && (
                      <p className="text-xs">Cancellation requested</p>
                    )}
                  </TableCell>
                  <TableCell>
                    {run.origin.kind}
                    {run.origin.scheduleId && (
                      <p className="text-xs">
                        Schedule {run.origin.scheduleId}
                      </p>
                    )}
                    {run.origin.triggerId && (
                      <p className="break-all text-xs">
                        Trigger {run.origin.triggerId}
                      </p>
                    )}
                    {run.origin.scheduledAt && (
                      <p className="text-xs">{run.origin.scheduledAt}</p>
                    )}
                  </TableCell>
                  <TableCell>
                    {new Date(run.createdAt).toLocaleString()}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ResourceTableFrame>
      ) : (
        <InventoryStatePanel title="No runs yet" />
      )}
    </InventoryPageShell>
  );
}
export function RunPage() {
  const { runId } = useParams();
  const run = usePlatformRun(runId);
  if (run.isPending) return <InventoryStatePanel title="Loading run…" />;
  if (!run.data)
    return <RequestError error={run.error} retry={() => void run.refetch()} />;
  return <RunInspector key={run.data.id} run={run.data} />;
}
function RunInspector({ run }: { run: RunDetail }) {
  const [search, setSearch] = useSearchParams();
  const [rerunId] = useState(() => crypto.randomUUID());
  const mutations = usePlatformMutations();
  const navigate = useNavigate();
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
              <Button
                disabled={mutations.rerun.isPending}
                onClick={() =>
                  void mutations.rerun
                    .mutateAsync({ id: run.id, launchId: rerunId })
                    .then((next) =>
                      navigate(`/runs/${encodeURIComponent(next.id)}`),
                    )
                    .catch(() => {})
                }
              >
                Rerun frozen snapshot
              </Button>
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
        <Tabs value={tab} onValueChange={(value) => setSearch({ tab: value })}>
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
                  evidenceId
                    ? { tab: "evidence", target: evidenceId }
                    : { tab: "evidence", node: nodeId },
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
                      to={`?tab=evidence&target=${encodeURIComponent(edge.evidenceId)}`}
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
