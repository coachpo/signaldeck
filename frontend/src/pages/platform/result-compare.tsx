import { useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useResultHistory, useRunResult } from "@/hooks/use-results";
import { useTaskReuse } from "@/hooks/use-task-experience";
import { useResultArtifactSelection } from "@/hooks/use-result-delivery";
import { Button } from "@/components/ui/button";
import { ChoiceField, TextField } from "@/components/shared/form-field";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { MarkdownContent } from "@/components/shared/markdown-content";
import { RequestError } from "./feedback";
import { ResultValue } from "./result-content";
import { confirmedContents, readableContent, type ConfirmedContent } from "./result-delivery";
import { compareText } from "./result-diff";
import { resultStatusLabels, originLabels } from "./result-labels";
import type { RunResult } from "@/lib/types/result";

export function ResultComparePage() {
  const [search, setSearch] = useSearchParams();
  const leftId = search.get("left") ?? "";
  const rightId = search.get("right") ?? "";
  return <InventoryPageShell pageContext={{ title: "比较两次结果", description: "固定两次运行并显式选择确认内容，查看文本差异。", actions: <Button asChild variant="outline"><Link to="/runs">全部结果</Link></Button> }}>
    <CompareSelection key={`selection:${leftId}:${rightId}`} left={leftId} right={rightId} onChoose={(left, right) => setSearch({ left, right })} />
    {leftId && leftId === rightId && <p>当前两侧选择的是同一次运行。</p>}
    {leftId && rightId ? <CompareResults key={`results:${leftId}:${rightId}`} leftId={leftId} rightId={rightId} /> : <p>请填写两次运行 ID 后固定比较。可从结果页进入并带入当前运行。</p>}
  </InventoryPageShell>;
}
function CompareSelection({ left, right, onChoose }: { left: string; right: string; onChoose: (left: string, right: string) => void }) {
  const [draftLeft, setLeft] = useState(left);
  const [draftRight, setRight] = useState(right);
  return <form className="flex flex-col gap-3" onSubmit={(event) => { event.preventDefault(); if (draftLeft.trim() && draftRight.trim()) onChoose(draftLeft.trim(), draftRight.trim()); }}>
    <div className="grid min-w-0 gap-3 md:grid-cols-2">
      <TextField label="左侧运行 ID" value={draftLeft} onChange={setLeft} />
      <TextField label="右侧运行 ID" value={draftRight} onChange={setRight} />
    </div>
    <HistoryChoices onChoose={(side, id) => side === "left" ? setLeft(id) : setRight(id)} />
    <Button variant="outline" type="submit" disabled={!draftLeft.trim() || !draftRight.trim()}>固定两次结果</Button>
  </form>;
}
function HistoryChoices({ onChoose }: { onChoose: (side: "left" | "right", id: string) => void }) {
  const [open, setOpen] = useState(false);
  return <div className="flex flex-col gap-2">
    <Button type="button" variant="ghost" aria-expanded={open} onClick={() => setOpen(!open)}>{open ? "收起结果选择" : "从结果记录选择"}</Button>
    {open && <HistoryChoiceList onChoose={onChoose} />}
  </div>;
}
function HistoryChoiceList({ onChoose }: { onChoose: (side: "left" | "right", id: string) => void }) {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState({ offset: 0, snapshotAt: "" });
  const search = new URLSearchParams({ q: query, limit: "10", offset: String(page.offset) });
  if (page.snapshotAt) search.set("snapshotAt", page.snapshotAt);
  const history = useResultHistory(search.toString());
  return <div className="flex flex-col gap-3">
    <TextField label="搜索结果记录" value={query} onChange={(value) => { setQuery(value); setPage({ offset: 0, snapshotAt: "" }); }} />
    <RequestError error={history.error} retry={() => void history.refetch()} />
    {history.isPending && <p>正在读取结果记录…</p>}
    {history.data && <>
      {!history.data.items.length && <p>没有符合条件的结果记录。</p>}
      <ul className="flex flex-col gap-3">
        {history.data.items.map((item) => <li key={item.id} className="flex flex-wrap items-center justify-between gap-2">
          <p className="min-w-0 break-words text-sm">{item.title} · {resultStatusLabels[item.status]} · {new Date(item.createdAt).toLocaleString()}<span className="block break-all text-xs text-muted-foreground">{item.id}</span></p>
          <div className="flex gap-2">
            <Button type="button" variant="outline" onClick={() => onChoose("left", item.id)} aria-label={`将 ${item.id} 选为左侧`}>选为左侧</Button>
            <Button type="button" variant="outline" onClick={() => onChoose("right", item.id)} aria-label={`将 ${item.id} 选为右侧`}>选为右侧</Button>
          </div>
        </li>)}
      </ul>
      <div className="flex gap-2">
        <Button type="button" variant="outline" disabled={!page.offset} onClick={() => setPage({ offset: Math.max(0, page.offset - 10), snapshotAt: history.data.snapshotAt })}>上一页结果</Button>
        <Button type="button" variant="outline" disabled={page.offset + history.data.items.length >= history.data.total} onClick={() => setPage({ offset: page.offset + 10, snapshotAt: history.data.snapshotAt })}>下一页结果</Button>
      </div>
    </>}
  </div>;
}
function CompareResults({ leftId, rightId }: { leftId: string; rightId: string }) {
  const left = useRunResult(leftId), right = useRunResult(rightId);
  const [search, setSearch] = useSearchParams();
  const leftArtifacts = useResultArtifactSelection(), rightArtifacts = useResultArtifactSelection();
  const leftOptions = left.data ? confirmedContents(left.data) : [];
  const rightOptions = right.data ? confirmedContents(right.data) : [];
  const chosenLeft = leftOptions.find((item) => item.id === search.get("leftSection"));
  const chosenRight = rightOptions.find((item) => item.id === search.get("rightSection"));
  const leftText = chosenLeft?.artifact ? leftArtifacts.loaded[chosenLeft.id] : chosenLeft?.text;
  const rightText = chosenRight?.artifact ? rightArtifacts.loaded[chosenRight.id] : chosenRight?.text;
  return <>
    <div className="grid min-w-0 gap-4 lg:grid-cols-2">
      {([{ side: "left", label: "左侧", query: left, options: leftOptions, chosen: chosenLeft, artifacts: leftArtifacts, text: leftText },
        { side: "right", label: "右侧", query: right, options: rightOptions, chosen: chosenRight, artifacts: rightArtifacts, text: rightText }] as const).map(({ side, label, query, options, chosen, artifacts, text }) => <section key={side} className="flex min-w-0 flex-col gap-3 rounded border border-border p-4" aria-label={`${label}结果`}>
        <h2 className="font-semibold">{label}结果</h2>
        {query.isPending && <p>正在加载结果…</p>}
        <RequestError error={query.error} retry={() => void query.refetch()} />
        {query.data && <>
          <ComparisonIdentity result={query.data} />
          {options.filter(readableContent).length ? <ChoiceField label={`${label}确认内容`} value={chosen?.id ?? ""} options={options.filter(readableContent).map((item) => ({ value: item.id, label: `${item.label}${item.artifact ? ` · 附件 ${item.artifact.sizeBytes} 字节` : ""}` }))} onChange={(value) => setSearch((previous) => { const next = new URLSearchParams(previous); next.set(`${side}Section`, value); return next; })} /> : <p>此运行没有可比较的确认正文。请打开原结果查看状态、附件或证据。</p>}
          {!!query.data.deferredSections?.length && <p>部分声明保存在产物中，请显式选择附件读取原文。</p>}
          {chosen?.artifact && text === undefined && <Button variant="outline" disabled={artifacts.pending.includes(chosen.id)} onClick={() => void artifacts.read(chosen)}>{artifacts.pending.includes(chosen.id) ? "正在读取…" : `读取${label}所选附件`}</Button>}
          {chosen && artifacts.errors[chosen.id] && <p role="alert">{artifacts.errors[chosen.id]}</p>}
          {chosen && text !== undefined && <ComparedContent item={chosen} text={text} />}
        </>}
      </section>)}
    </div>
    <TextDifference leftText={leftText} rightText={rightText} />
  </>;
}
function TextDifference({ leftText, rightText }: { leftText?: string; rightText?: string }) {
  const diff = useMemo(() => leftText !== undefined && rightText !== undefined ? compareText(leftText, rightText) : null, [leftText, rightText]);
  return <section className="flex min-w-0 flex-col gap-3" aria-label="文本差异">
      <h2 className="font-semibold">文本差异</h2>
      <p className="text-sm">只比较所选确认内容的文本，不推断业务变化。两侧运行身份与状态独立保留。</p>
      {!diff ? <p>请选择两侧确认内容；附件需先显式读取。</p> : <>
        {leftText === rightText && <p>所选正文相同；运行身份、输入、修订与来源仍可能不同。</p>}
        {diff.coarse && <p>变更区域较长，按整段显示删除与新增；原文完整保留。</p>}
        <div className="flex flex-col gap-2">
          {diff.blocks.map((block, index) => <div key={index}>
            <p className="text-xs text-muted-foreground">{block.kind === "same" ? "相同" : block.kind === "removed" ? "左侧删除" : "右侧新增"}</p>
            <pre tabIndex={0} className="max-h-96 max-w-full overflow-auto rounded bg-ui-surface-inset p-3 text-xs">{block.text}</pre>
          </div>)}
        </div>
      </>}
    </section>;
}
function ComparedContent({ item, text }: { item: ConfirmedContent; text: string }) {
  return item.format === "markdown" ? <MarkdownContent>{text}</MarkdownContent> : <pre tabIndex={0} className="max-h-96 max-w-full overflow-auto rounded bg-ui-surface-inset p-3 text-xs">{text}</pre>;
}
function ComparisonIdentity({ result }: { result: RunResult }) {
  const original = useTaskReuse(result.runId);
  return <div className="flex min-w-0 flex-col gap-2 text-sm">
    <Link className="break-all underline" to={`/runs/${encodeURIComponent(result.runId)}`}>{result.title} · {result.runId}</Link>
    <p>状态：{resultStatusLabels[result.status] ?? result.status} · 内容：{result.contentStatus}</p>
    {!!result.readUnknownEvidenceIds?.length && <p>读取结果未确认；当前仅比较已确认内容，该读取不涉及保存。</p>}
    {result.contentStatus === "unknown" && <p>保存状态待核实；当前仅比较已确认内容。</p>}
    {result.cancelRequestedAt && <p>已请求取消；已确认的外部操作仍会保留。</p>}
    {(result.status === "queued" || result.status === "running") && <p>执行尚未结束，确认内容可能继续更新。</p>}
    <p>来源：{originLabels[result.origin.kind]} · 数据时间：{result.dataTime ?? "未提供"}</p>
    <p>创建：{result.createdAt} · 完成：{result.finishedAt ?? "尚未结束"}</p>
    {original.isPending && <p>正在读取冻结修订与输入…</p>}
    <RequestError error={original.error} retry={() => void original.refetch()} />
    {original.data && <>
      <p className="break-all">修订：{original.data.packageHash} · {original.data.packageKey} / {original.data.workflowKey}</p>
      <p className="break-words">输入摘要：{JSON.stringify(original.data.parameters).slice(0, 180)}{JSON.stringify(original.data.parameters).length > 180 ? "…（展开查看完整输入）" : ""}</p>
      <details><summary className="cursor-pointer">完整输入</summary><ResultValue value={original.data.parameters} /></details>
    </>}
    {result.missing.length > 0 && <p>缺失资料：{result.missing.join("、")}</p>}
    <details><summary className="cursor-pointer">资料来源与新鲜度</summary><ResultValue value={result.sources} /><ResultValue value={result.freshness} /><ResultValue value={result.origin as unknown as import("@/lib/types/workflow-platform").Json} /></details>
  </div>;
}
