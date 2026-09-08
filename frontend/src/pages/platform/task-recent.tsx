import { Link } from "react-router";
import { useResultHistory } from "@/hooks/use-results";
const statuses: Record<string, string> = {
  queued: "等待执行",
  running: "执行中",
  succeeded: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
  timed_out: "已超时",
};
export function TaskRecent({
  packageKey,
  workflowKey,
}: {
  packageKey: string;
  workflowKey: string;
}) {
  const query = useResultHistory(
    new URLSearchParams({
      packageKey,
      workflowKey,
      limit: "1",
      offset: "0",
      sort: "created_desc",
    }).toString(),
  );
  const last = query.data?.items[0];
  return (
    <p className="text-sm text-muted-foreground">
      {query.isPending ? (
        "正在读取最近使用…"
      ) : query.error ? (
        "最近使用记录暂时不可用"
      ) : last ? (
        <Link
          className="underline underline-offset-4"
          to={`/runs/${encodeURIComponent(last.id)}`}
        >
          最近使用：{new Date(last.createdAt).toLocaleString()} ·{" "}
          {statuses[last.status] ?? last.status}
        </Link>
      ) : (
        "尚无执行记录"
      )}
    </p>
  );
}
