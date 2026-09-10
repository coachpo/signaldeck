import { Link } from "react-router";
import { useTaskDrafts } from "@/hooks/use-task-drafts";
import { RequestError } from "./feedback";
export function TaskDraftList() {
  const drafts = useTaskDrafts();
  return <section className="flex flex-col gap-2" aria-label="已保存草稿">
    <h2 className="font-medium">已保存草稿</h2>
    <RequestError error={drafts.error} retry={() => void drafts.refetch()} />
    {drafts.isPending && <p role="status">正在读取草稿…</p>}
    {drafts.data?.items.length === 0 && <p className="text-sm text-muted-foreground">尚未保存草稿。草稿可以保留未完成的输入。</p>}
    {drafts.data?.items.map(draft => <div key={draft.id} className="flex flex-wrap gap-3 text-sm">
      <Link className="underline" to={`/tasks/new?draftId=${encodeURIComponent(draft.id)}`}>{draft.name}</Link>
      <span>{draft.pending ? "启动待核实" : "可恢复"} · 修订 {draft.revision} · {new Date(draft.updatedAt).toLocaleString()}</span>
    </div>)}
  </section>;
}
