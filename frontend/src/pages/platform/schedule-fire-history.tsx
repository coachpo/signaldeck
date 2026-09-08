import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardDescription,
} from "@/components/ui/card";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { useScheduleFires } from "@/hooks/use-workflow-platform";
import { RequestError } from "./feedback";
export function ScheduleFireHistory({ scheduleId }: { scheduleId: string }) {
  const query = useScheduleFires(scheduleId);
  return (
    <Card>
      <CardHeader>
        <CardTitle>Fire history</CardTitle>
        <CardDescription>
          Each fire retains its own identity, launch outcome and linked
          execution.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Button variant="outline" onClick={() => void query.refetch()}>
          Refresh fire history
        </Button>
        <RequestError error={query.error} />
        {query.isPending && (
          <InventoryStatePanel title="Loading fire history…" />
        )}
        {query.data?.items.length === 0 && (
          <InventoryStatePanel title="No fires recorded" />
        )}
        {query.data?.items.map((fire) => (
          <article
            key={fire.triggerId}
            className="flex min-w-0 flex-col gap-2 rounded-lg bg-ui-surface-grouped p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <ResourceStatusBadge
                label={fire.status}
                tone={
                  ["failed", "launch_failed"].includes(fire.status)
                    ? "danger"
                    : "neutral"
                }
              />
              <time dateTime={fire.scheduledAt}>
                {new Date(fire.scheduledAt).toLocaleString()}
              </time>
              {fire.runId ? (
                <Button asChild variant="outline">
                  <Link to={`/runs/${encodeURIComponent(fire.runId)}`}>
                    Inspect run {fire.runId}
                  </Link>
                </Button>
              ) : (
                <span className="text-sm text-muted-foreground">
                  Run not created
                </span>
              )}
            </div>
            <code className="break-all text-xs">Fire {fire.triggerId}</code>
            <p className="break-all text-xs text-muted-foreground">
              Engine workflow {fire.engineWorkflowId} · execution{" "}
              {fire.engineRunId}
            </p>
            {fire.errorCode && (
              <p className="text-sm text-destructive">{fire.errorCode}</p>
            )}
          </article>
        ))}
      </CardContent>
    </Card>
  );
}
