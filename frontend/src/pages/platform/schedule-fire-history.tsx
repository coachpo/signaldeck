import { scheduleFireLabel } from "@/lib/schedule-frequency";
import { useDisplayMode } from "@/hooks/use-display-mode";
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
  const { expert } = useDisplayMode();
  return (
    <Card>
      <CardHeader>
        <CardTitle>执行记录</CardTitle>
        <CardDescription>
          每次执行保留独立来源、实际状态和对应结果。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <Button variant="outline" onClick={() => void query.refetch()}>
          刷新执行记录
        </Button>
        <RequestError error={query.error} />
        {query.isPending && <InventoryStatePanel title="正在读取执行记录…" />}
        {query.data?.items.length === 0 && (
          <InventoryStatePanel title="暂无执行记录" />
        )}
        {query.data?.items.map((fire) => (
          <article
            key={fire.triggerId}
            className="flex min-w-0 flex-col gap-2 rounded-lg bg-ui-surface-grouped p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <ResourceStatusBadge
                label={scheduleFireLabel(fire.status)}
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
                    查看结果
                  </Link>
                </Button>
              ) : (
                <span className="text-sm text-muted-foreground">
                  尚未生成结果
                </span>
              )}
            </div>
            <details open={expert}>
              <summary className="cursor-pointer text-xs">技术来源</summary>
              <code className="break-all text-xs">Fire {fire.triggerId}</code>
              <p className="break-all text-xs text-muted-foreground">
                Engine workflow {fire.engineWorkflowId} · execution{" "}
                {fire.engineRunId}
              </p>
            </details>
            {fire.errorCode && (
              <p className="text-sm text-destructive">{fire.errorCode}</p>
            )}
          </article>
        ))}
      </CardContent>
    </Card>
  );
}
