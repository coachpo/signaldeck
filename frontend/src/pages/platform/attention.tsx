import { Link, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { useAttention, useMarkAttention } from "@/hooks/use-result-metadata";
import { resultStatusLabels } from "./result-labels";
import { ExecutionDiagnostic } from "./execution-diagnostic";
import { RequestError } from "./feedback";

export function AttentionPage() {
  const [search, setSearch] = useSearchParams();
  const query = new URLSearchParams(search);
  query.set("limit", "25");
  const records = useAttention(query.toString());
  const mark = useMarkAttention();
  const offset = Math.max(0, Number(search.get("offset")) || 0);
  const view = search.get("view") ?? "attention";
  function page(value: number) {
    const next = new URLSearchParams(search);
    next.set("offset", String(value));
    if (records.data?.snapshotAt) next.set("snapshotAt", records.data.snapshotAt);
    setSearch(next);
  }
  return <InventoryPageShell pageContext={{ title: "执行更新", description: "查看完成、失败和待核实的执行记录", actions: <Button variant="outline" onClick={() => { const next = new URLSearchParams(search); next.delete("offset"); next.delete("snapshotAt"); setSearch(next); void records.refetch(); }}>刷新更新</Button> }}>
    <p className="text-sm text-muted-foreground">首次打开包含所有已有记录的当前状态。状态变化会形成新的未读更新；已查看的待核实操作仍会显示。结果标为已读时也会确认当时的更新。</p>
    <div className="flex flex-wrap gap-2">
      <Button variant={view === "attention" ? "default" : "outline"} onClick={() => setSearch({ view: "attention" })}>未读与待核实</Button>
      <Button variant={view === "all" ? "default" : "outline"} onClick={() => setSearch({ view: "all" })}>全部更新</Button>
    </div>
    <RequestError error={records.error || mark.error} retry={() => { mark.reset(); void records.refetch(); }} />
    {records.isPending && <InventoryStatePanel title="正在读取执行更新…" />}
    {records.data?.items.length === 0 && <InventoryStatePanel title="暂无执行更新" />}
    {records.data?.items.map((item) => <article key={item.id} className="flex min-w-0 flex-col gap-3 rounded border border-border bg-card p-4">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-medium">{item.title}</h2>
        <ResourceStatusBadge label={item.kind === "fire" ? "未能启动" : resultStatusLabels[item.status] ?? item.status} />
        <span className="text-sm">{item.isRead ? "更新已查看" : "新更新"}</span>
      </div>
      <time className="text-sm text-muted-foreground" dateTime={item.occurredAt}>{new Date(item.occurredAt).toLocaleString()}</time>
      {item.hasUnknownEffects && <p className="text-sm">保存状态待核实。请核对目标位置和执行证据；标为已查看不会确认操作成功。</p>}
      {item.errorCode && <ExecutionDiagnostic code={item.errorCode} category={item.errorCategory} />}
      <div className="flex flex-wrap gap-2">
        {item.runId && <Button asChild variant="outline"><Link to={`/runs/${encodeURIComponent(item.runId)}`}>查看结果</Link></Button>}
        {item.hasUnknownEffects && item.runId && <Button asChild variant="outline"><Link to={`/runs/${encodeURIComponent(item.runId)}?tab=evidence`}>核实执行证据</Link></Button>}
        {item.scheduleId && <Button asChild variant="outline"><Link to={`/scheduled-tasks/${encodeURIComponent(item.scheduleId)}`}>查看安排与失败原因</Link></Button>}
        <Button variant="outline" disabled={mark.isPending} onClick={() => void mark.mutateAsync({ id: item.id, revision: item.revision, isRead: !item.isRead }).catch(() => {})}>{item.isRead ? "将本次更新标为未查看" : "已查看本次更新"}</Button>
      </div>
      {item.triggerId && <details><summary className="cursor-pointer text-sm">执行来源</summary><code className="break-all">Fire {item.triggerId}</code></details>}
    </article>)}
    {records.data && <nav aria-label="执行更新分页" className="flex items-center justify-between gap-2">
      <Button variant="outline" disabled={offset === 0 || records.isFetching} onClick={() => page(Math.max(0, offset - 25))}>上一页</Button>
      <span className="text-sm">共 {records.data.total} 条更新</span>
      <Button variant="outline" disabled={offset + 25 >= records.data.total || records.isFetching} onClick={() => page(offset + 25)}>下一页</Button>
    </nav>}
  </InventoryPageShell>;
}
