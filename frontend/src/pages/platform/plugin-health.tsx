import { Link } from "react-router";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import type { Plugin } from "@/lib/types/workflow-platform";
const labels = { not_observed: "尚未使用", succeeded: "最近使用成功", failed: "最近使用失败", unknown: "最近结果未确认" };
export function PluginHealth({ health }: { health: Plugin["health"] }) {
  return <section aria-label="最近使用情况" className="flex min-w-0 flex-col gap-2">
    <h3 className="text-sm font-medium">最近使用情况</h3>
    {!health.observedAt ? <p className="text-sm text-muted-foreground">尚无使用记录，是否可用需要通过任务执行确认。</p> : <>
      <div className="flex flex-wrap items-center gap-2"><ResourceStatusBadge label={labels[health.status]} tone={health.status === "failed" ? "danger" : "neutral"} /><time dateTime={health.observedAt} className="text-sm text-muted-foreground">{new Date(health.observedAt).toLocaleString()}</time></div>
      {health.status === "failed" && <p className="text-sm text-destructive">上次未能完成。请检查服务是否可用及账户权限，恢复后再试。</p>}
      {health.status === "unknown" && <p className="text-sm">尚不能确认服务是否完成了操作。请先核对资料与任务记录，再决定是否重试。</p>}
      {health.runId && <Link className="text-sm underline" to={`/runs/${encodeURIComponent(health.runId)}${health.evidenceId ? `?tab=evidence&target=${encodeURIComponent(health.evidenceId)}` : ""}`}>查看最近任务记录</Link>}
    </>}
  </section>;
}
