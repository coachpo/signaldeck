import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import type {
  ExecutionEvidence,
  WorkflowPlan,
} from "@/lib/types/workflow-platform";
export function DependencyGraph({
  plan,
  evidence,
  onSelect,
}: {
  plan: WorkflowPlan;
  evidence?: ExecutionEvidence[];
  onSelect?: (nodeId: string, evidenceId?: string) => void;
}) {
  const levels = new Map<string, number>();
  for (const key of plan.nodeOrder)
    levels.set(
      key,
      Math.max(
        0,
        ...(plan.dependencies[key] ?? []).map(
          (dep) => (levels.get(dep) ?? 0) + 1,
        ),
      ),
    );
  const columns = Array.from(new Set(levels.values()));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Workflow graph</CardTitle>
        <CardDescription>
          {plan.workflowKey} · dependency readiness and edge sources
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div className="flex gap-4 overflow-auto" aria-label="Workflow nodes">
          {columns.map((level) => (
            <div key={level} className="flex min-w-40 flex-col gap-3">
              {plan.nodeOrder
                .filter((key) => levels.get(key) === level)
                .map((key) => {
                  const node = (evidence ?? [])
                    .filter((e) => e.nodeId === key && e.kind === "node")
                    .sort((a, b) => b.attempt - a.attempt)[0];
                  return (
                    <div
                      key={key}
                      className="flex flex-col gap-2 rounded-lg bg-ui-surface-grouped p-3"
                    >
                      <Button
                        variant="outline"
                        onClick={() => onSelect?.(key, node?.id)}
                      >
                        {key}
                      </Button>
                      <ResourceStatusBadge
                        label={
                          node?.status ?? (evidence ? "no evidence" : "defined")
                        }
                        tone={node?.status === "failed" ? "danger" : "neutral"}
                      />
                      {node?.errorCode && (
                        <span className="text-xs text-destructive">
                          {node.errorCode}
                        </span>
                      )}
                    </div>
                  );
                })}
            </div>
          ))}
        </div>
        <ul
          aria-label="Dependency edges"
          className="flex flex-col gap-2 text-sm"
        >
          {plan.edges.map((edge) => (
            <li
              key={`${edge.source}:${edge.target}`}
              className="flex flex-wrap items-center gap-2"
            >
              <span>
                {edge.source} → {edge.target}
              </span>
              {edge.sources.map((source) => (
                <ResourceStatusBadge key={source} label={source} />
              ))}
              <span className="break-all text-xs text-muted-foreground">
                {edge.paths.join(", ")}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
