import { Link } from "react-router";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import type { Plugin } from "@/lib/types/workflow-platform";
export function PluginHealth({ health }: { health: Plugin["health"] }) {
  return (
    <section
      aria-label="Last observed call"
      className="flex min-w-0 flex-col gap-2"
    >
      <h3 className="text-sm font-medium">Last observed call</h3>
      {!health.observedAt ? (
        <p className="text-sm text-muted-foreground">No observations</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2">
            <ResourceStatusBadge
              label={health.status}
              tone={health.status === "failed" ? "danger" : "neutral"}
            />
            <time
              dateTime={health.observedAt}
              className="text-sm text-muted-foreground"
            >
              {health.observedAt}
            </time>
          </div>
          {health.errorCode && (
            <p className="text-sm text-destructive">{health.errorCode}</p>
          )}
          {health.runId && (
            <Link
              className="break-all text-sm underline"
              to={`/runs/${encodeURIComponent(health.runId)}${health.evidenceId ? `?tab=evidence&target=${encodeURIComponent(health.evidenceId)}` : ""}`}
            >
              Inspect recorded call in {health.runId}
            </Link>
          )}
          {health.operationId && (
            <code className="break-all text-xs">
              Operation {health.operationId}
            </code>
          )}
        </>
      )}
    </section>
  );
}
