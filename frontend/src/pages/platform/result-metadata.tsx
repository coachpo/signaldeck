import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Field, FieldGroup } from "@/components/shared/form-field";
import { InlineStatePanel } from "@/components/shared/inline-state-panel";
import { useResultMetadata, usePatchResultMetadata } from "@/hooks/use-result-metadata";
import type { ResultMetadata } from "@/lib/types/result-metadata";
import { ApiRequestError } from "@/lib/api-client";
import { RequestError } from "./feedback";

export function ResultMetadataControls({ runId }: { runId: string }) {
  const query = useResultMetadata(runId);
  if (query.isPending) return <p className="text-sm text-muted-foreground">正在读取个人标记…</p>;
  if (!query.data) return <RequestError error={query.error} retry={() => void query.refetch()} />;
  return <MetadataEditor key={runId} metadata={query.data} refresh={() => void query.refetch()} />;
}
function MetadataEditor({ metadata, refresh }: { metadata: ResultMetadata; refresh: () => void }) {
  const mutation = usePatchResultMetadata(metadata.runId);
  const [draft, setDraft] = useState<{ note: string; revision: number } | null>(null);
  const conflict = mutation.error instanceof ApiRequestError && mutation.error.status === 409;
  function patch(changes: { isFavorite?: boolean; isRead?: boolean }) {
    void mutation.mutateAsync({ expectedRevision: metadata.revision, ...changes }).catch(() => {});
  }
  return <section aria-label="个人结果标记" className="flex min-w-0 flex-col gap-3 border-y border-border py-4">
    <h2 className="font-semibold">个人标记与备注</h2>
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" aria-pressed={metadata.isFavorite} disabled={mutation.isPending} onClick={() => patch({ isFavorite: !metadata.isFavorite })}>
        {metadata.isFavorite ? "取消收藏" : "收藏结果"}
      </Button>
      <Button variant="outline" disabled={mutation.isPending} onClick={() => patch({ isRead: !metadata.isRead })}>
        {metadata.isRead ? "标为未读" : "标为已读"}
      </Button>
      {!draft && <Button variant="outline" onClick={() => { mutation.reset(); setDraft({ note: metadata.note, revision: metadata.revision }); }}>编辑个人备注</Button>}
    </div>
    <p className="text-sm text-muted-foreground">{metadata.isRead ? "结果已读" : "结果未读"}。个人备注与执行正文分别保存；标为已读同时确认当前更新，后续状态变化仍会提示。</p>
    {metadata.note && <p className="whitespace-pre-wrap break-words text-sm">{metadata.note}</p>}
    {conflict ? <InlineStatePanel tone="warning" title="个人标记已在其他窗口更新" description="你的备注草稿仍保留。先读取最新标记，核对后再保存。">
      <Button variant="outline" onClick={refresh}>读取最新标记</Button>
    </InlineStatePanel> : <RequestError error={mutation.error} />}
    {draft && <FieldGroup>
      <Field label="个人备注" description="清空后保存可删除备注；不会修改执行结果。">
        <Textarea aria-label="个人备注" maxLength={20000} value={draft.note} onChange={(event) => setDraft({ ...draft, note: event.target.value })} />
      </Field>
      {draft.revision !== metadata.revision && <InlineStatePanel tone="warning" title="保存版本已变化" description={`最新已保存备注：${metadata.note || "（空）"}`}>
        <Button variant="outline" onClick={() => { setDraft({ ...draft, revision: metadata.revision }); mutation.reset(); }}>已核对，保留草稿并使用最新版本</Button>
      </InlineStatePanel>}
      <div className="flex flex-wrap gap-2">
        <Button disabled={mutation.isPending || draft.revision !== metadata.revision} onClick={() => void mutation.mutateAsync({ expectedRevision: draft.revision, note: draft.note }).then(() => setDraft(null)).catch(() => {})}>保存个人备注</Button>
        <Button variant="outline" disabled={mutation.isPending} onClick={() => { setDraft(null); mutation.reset(); }}>取消编辑</Button>
      </div>
    </FieldGroup>}
  </section>;
}

export function HistoryResultMarks({ metadata, title }: { metadata: ResultMetadata; title: string }) {
  const mutation = usePatchResultMetadata(metadata.runId);
  return <div className="flex flex-col gap-1">
    <div className="flex flex-wrap gap-1">
      <Button size="sm" variant="outline" disabled={mutation.isPending} aria-label={`${metadata.isFavorite ? "取消收藏" : "收藏"} ${title}`} onClick={() => void mutation.mutateAsync({ expectedRevision: metadata.revision, isFavorite: !metadata.isFavorite }).catch(() => {})}>{metadata.isFavorite ? "取消收藏" : "收藏"}</Button>
      <Button size="sm" variant="outline" disabled={mutation.isPending} aria-label={`${metadata.isRead ? "标为未读" : "标为已读"} ${title}`} onClick={() => void mutation.mutateAsync({ expectedRevision: metadata.revision, isRead: !metadata.isRead }).catch(() => {})}>{metadata.isRead ? "标为未读" : "标为已读"}</Button>
    </div>
    {mutation.error && <p role="alert" className="text-sm text-destructive">标记未保存，请核对最新状态后重试。</p>}
  </div>;
}
