import { Link } from "react-router";
import type { Json } from "@/lib/types/workflow-platform";
import { objectValue, recordedTime } from "./result-context";

export function ResultFreshness({ value }: { value: Json }) {
  const record = objectValue(value);
  if (!record || typeof record.hit !== "boolean") return null;
  return <section className="flex flex-col gap-2 rounded bg-ui-surface-grouped p-3 text-sm" aria-label="资料获取记录">
    <p className="font-medium">{record.hit ? "沿用此前取得的资料" : "本次重新取得资料"}</p>
    {typeof record.sourceRunId === "string" && <Link className="underline" to={`/runs/${encodeURIComponent(record.sourceRunId)}`}>查看资料来源任务</Link>}
    {typeof record.sourceRunId === "string" && typeof record.sourceOperationId === "string" && <Link className="underline" to={`/runs/${encodeURIComponent(record.sourceRunId)}?${new URLSearchParams({ tab: "evidence", operation: record.sourceOperationId })}`}>查看资料来源步骤</Link>}
    <p>取得时间：{recordedTime(typeof record.fetchedAt === "string" ? record.fetchedAt : null)}</p>
    <p>可复用至：{recordedTime(typeof record.expiresAt === "string" ? record.expiresAt : null)}</p>
  </section>;
}
