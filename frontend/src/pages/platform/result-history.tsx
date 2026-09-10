import { HistoryResultMarks } from "./result-metadata";
import { Link, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { ResourceToolbar } from "@/components/shared/resource-toolbar";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useResultHistory,
  useInvalidateResultHistory,
} from "@/hooks/use-results";
import { availableTasks } from "./task-catalog";
import { usePackages } from "@/hooks/use-workflow-platform";
import { localDateBoundary, localDateValue } from "./result-history-query";
import { RequestError } from "./feedback";
import { originLabels, resultStatusLabels } from "./result-labels";
const selectClass =
  "h-8 min-w-0 rounded border border-input bg-background px-2 text-sm";
export function ResultHistoryPage() {
  const packages = usePackages();
  const tasks = availableTasks(packages.data?.items ?? []);
  const [search, setSearch] = useSearchParams();
  const invalidateHistory = useInvalidateResultHistory();
  const query = new URLSearchParams(search);
  query.set("limit", "25");
  const runs = useResultHistory(query.toString());
  const offset = Math.max(0, Number(search.get("offset")) || 0);
  function change(key: string, value: string) {
    const next = new URLSearchParams(search);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "offset") {
      next.delete("offset");
      next.delete("snapshotAt");
    } else if (runs.data?.snapshotAt)
      next.set("snapshotAt", runs.data.snapshotAt);
    setSearch(next);
  }
  async function refresh() {
    if (search.has("offset") || search.has("snapshotAt")) {
      const next = new URLSearchParams(search);
      next.delete("offset");
      next.delete("snapshotAt");
      const refreshedQuery = new URLSearchParams(next);
      refreshedQuery.set("limit", "25");
      await invalidateHistory(refreshedQuery.toString());
      setSearch(next);
    } else void runs.refetch();
  }
  return (
    <InventoryPageShell
      pageContext={{
        title: "结果",
        description: "查找和阅读所有执行记录",
        actions: (
          <div className="flex flex-wrap gap-2"><Button asChild variant="outline"><Link to="/attention">执行更新</Link></Button><Button variant="outline" onClick={() => void refresh()}>刷新</Button></div>
        ),
      }}
    >
      <div className="flex flex-wrap gap-2" role="group" aria-label="结果分组">
        {[
          ["", "全部结果"],
          ["active", "进行中"],
          ["attention", "需要处理"],
        ].map(([value, label]) => (
          <Button
            key={value}
            variant={
              (search.get("group") ?? "") === value ? "default" : "outline"
            }
            onClick={() => change("group", value)}
          >
            {label}
          </Button>
        ))}
      </div>
      <ResourceToolbar
        search={{
          id: "result-search",
          label: "搜索全部历史",
          placeholder: "搜索标题或任务",
          value: search.get("q") ?? "",
          onChange: (value) => change("q", value),
        }}
        filters={
          <>
            <select aria-label="收藏筛选" className={selectClass} value={search.get("isFavorite") ?? ""} onChange={(e) => change("isFavorite", e.target.value)}>
              <option value="">全部收藏状态</option><option value="true">已收藏</option><option value="false">未收藏</option>
            </select>
            <select aria-label="阅读筛选" className={selectClass} value={search.get("isRead") ?? ""} onChange={(e) => change("isRead", e.target.value)}>
              <option value="">全部阅读状态</option><option value="false">未读</option><option value="true">已读</option>
            </select>
            <select
              aria-label="执行状态"
              className={selectClass}
              value={search.get("status") ?? ""}
              onChange={(e) => change("status", e.target.value)}
            >
              <option value="">所有状态</option>
              {["queued", "running", "succeeded", "failed", "cancelled"].map(
                (s) => (
                  <option key={s} value={s}>
                    {resultStatusLabels[s]}
                  </option>
                ),
              )}
            </select>
            <select
              aria-label="任务类型"
              className={selectClass}
              value={`${search.get("packageKey") ?? ""}/${search.get("workflowKey") ?? ""}`}
              onChange={(e) => {
                const [pkg, workflow] = e.target.value.split("/");
                const next = new URLSearchParams(search);
                next.delete("offset");
                next.delete("snapshotAt");
                if (pkg) next.set("packageKey", pkg);
                else next.delete("packageKey");
                if (workflow) next.set("workflowKey", workflow);
                else next.delete("workflowKey");
                setSearch(next);
              }}
            >
              <option value="/">所有任务</option>
              {tasks.map((t) => (
                <option
                  key={`${t.packageKey}/${t.workflowKey}`}
                  value={`${t.packageKey}/${t.workflowKey}`}
                >
                  {t.title}
                </option>
              ))}
            </select>
            <select
              aria-label="执行来源"
              className={selectClass}
              value={search.get("origin") ?? ""}
              onChange={(e) => change("origin", e.target.value)}
            >
              <option value="">所有来源</option>
              {Object.entries(originLabels).map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
            <label className="flex items-center gap-1 text-xs">
              起始日期
              <Input
                aria-label="起始日期"
                type="date"
                value={localDateValue(search.get("createdFrom"))}
                onChange={(e) =>
                  change("createdFrom", localDateBoundary(e.target.value))
                }
              />
            </label>
            <label className="flex items-center gap-1 text-xs">
              结束日期
              <Input
                aria-label="结束日期"
                type="date"
                value={localDateValue(search.get("createdTo"))}
                onChange={(e) =>
                  change("createdTo", localDateBoundary(e.target.value, true))
                }
              />
            </label>
            <select
              aria-label="排序"
              className={selectClass}
              value={search.get("sort") ?? "created_desc"}
              onChange={(e) => change("sort", e.target.value)}
            >
              <option value="created_desc">最新在前</option>
              <option value="created_asc">最早在前</option>
              <option value="title_asc">标题升序</option>
              <option value="title_desc">标题降序</option>
            </select>
          </>
        }
        resultSummary={
          runs.data ? `共 ${runs.data.total} 条记录` : "正在查询全部历史"
        }
        actions={
          <Button variant="ghost" onClick={() => setSearch({})}>
            清除筛选
          </Button>
        }
      />
      <RequestError error={runs.error} retry={() => void runs.refetch()} />
      {runs.isPending ? (
        <InventoryStatePanel title="正在加载结果…" />
      ) : runs.data?.items.length ? (
        <ResourceTableFrame>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>标题</TableHead>
                <TableHead>状态</TableHead>
                <TableHead>任务</TableHead>
                <TableHead>来源</TableHead>
                <TableHead>时间</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {runs.data.items.map((run) => (
                <TableRow key={run.id}>
                  <TableCell>
                    <Link
                      className="font-medium underline-offset-4 hover:underline"
                      to={`/runs/${encodeURIComponent(run.id)}?history=${encodeURIComponent(search.toString())}`}
                    >
                      {run.title}
                    </Link>
                    <p className="text-xs text-muted-foreground">{run.metadata?.isFavorite ? "已收藏 · " : ""}{run.metadata?.isRead ? "已读" : "未读"}{run.metadata?.note ? " · 有个人备注" : ""}</p>
                  </TableCell>
                  <TableCell>
                    <ResourceStatusBadge
                      label={resultStatusLabels[run.status] ?? run.status}
                    />
                    {run.hasUnknownEffects && (
                      <ResourceStatusBadge label="保存状态待核实" />
                    )}
                    {run.cancelRequestedAt &&
                      ["queued", "running"].includes(run.status) && (
                        <p className="text-xs">已请求取消，等待停止</p>
                      )}
                  </TableCell>
                  <TableCell>
                    {tasks.find((t) => t.packageKey === run.packageKey && t.workflowKey === run.workflowKey)?.title ??
                      run.workflowKey}
                  </TableCell>
                  <TableCell>{originLabels[run.origin.kind]}</TableCell>
                  <TableCell>
                    {new Date(run.createdAt).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    {run.metadata && <HistoryResultMarks metadata={run.metadata} title={run.title} />}
                    <Button asChild variant="link">
                      <Link
                        to={`/tasks/new?fromRun=${encodeURIComponent(run.id)}`}
                      >
                        修改输入
                      </Link>
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ResourceTableFrame>
      ) : (
        !runs.error && (
          <InventoryStatePanel
            title="没有符合条件的结果"
            description="尝试清除筛选，或从任务页开始一次任务。"
          />
        )
      )}
      {runs.data && (
        <nav
          aria-label="结果分页"
          className="flex items-center justify-between gap-2"
        >
          <Button
            variant="outline"
            disabled={offset === 0 || runs.isFetching}
            onClick={() => change("offset", String(Math.max(0, offset - 25)))}
          >
            上一页
          </Button>
          <span className="text-sm">
            第 {Math.floor(offset / 25) + 1} 页 · 共{" "}
            {Math.max(1, Math.ceil(runs.data.total / 25))} 页
          </span>
          <Button
            variant="outline"
            disabled={offset + 25 >= runs.data.total || runs.isFetching}
            onClick={() => change("offset", String(offset + 25))}
          >
            下一页
          </Button>
        </nav>
      )}
    </InventoryPageShell>
  );
}
