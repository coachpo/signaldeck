import { useState } from "react";
import { Button } from "@/components/ui/button";
import { useResultArtifactSelection } from "@/hooks/use-result-delivery";
import type { RunResult } from "@/lib/types/result";
import { confirmedContents, downloadMarkdown, exportMarkdown, readableContent } from "./result-delivery";

export function ResultExport({ result }: { result: RunResult }) {
  const options = confirmedContents(result);
  const [choices, setChoices] = useState<Record<string, boolean>>({});
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);
  const artifacts = useResultArtifactSelection();
  const selected = options.filter((item) => choices[item.id] ?? !item.artifact);
  async function deliver(copy: boolean) {
    setStatus("");
    setBusy(true);
    try {
      const text = exportMarkdown(result, selected, artifacts.loaded);
      if (copy) {
        await navigator.clipboard.writeText(text);
        setStatus("所选确认内容已复制。");
      } else {
        downloadMarkdown(result.runId, text);
        setStatus("已请求下载所选确认内容。");
      }
    } catch {
      setStatus(copy ? "复制失败。请检查剪贴板权限，或重试／导出 Markdown。" : "导出失败。请检查所选附件已读取，或重试／复制正文。");
    } finally {
      setBusy(false);
    }
  }
  const unread = selected.some((item) => item.artifact && artifacts.loaded[item.id] === undefined);
  return <section className="flex min-w-0 flex-col gap-3" aria-label="复制与导出">
    <details>
      <summary className="cursor-pointer">选择复制与导出的内容（已选 {selected.length} / {options.length} 项）</summary>
      <div className="flex flex-col gap-3 py-3">
        {options.map((item) => <div key={item.id} className="flex flex-col gap-2">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={choices[item.id] ?? !item.artifact} disabled={!readableContent(item)} onChange={(event) => {
              const checked = event.target.checked;
              setChoices((choices) => ({ ...choices, [item.id]: checked }));
              setStatus("");
              if (checked && item.artifact && artifacts.loaded[item.id] === undefined) void artifacts.read(item);
            }} />
            {item.artifact ? "读取并选入附件：" : ""}{item.label}
            {item.artifact && `（${item.artifact.mediaType}，${item.artifact.sizeBytes} 字节）`}
          </label>
          {item.artifact && !readableContent(item) && <p className="text-sm">此格式请使用原附件下载。</p>}
          {artifacts.pending.includes(item.id) && <p role="status">正在读取所选附件…</p>}
          {artifacts.errors[item.id] && <div role="alert"><p>{artifacts.errors[item.id]}</p><Button variant="outline" onClick={() => void artifacts.read(item)}>重试读取</Button></div>}
        </div>)}
      </div>
    </details>
    {options.some((item) => item.artifact) && <p className="text-sm text-muted-foreground">附件需显式读取选入；未选内容会在导出文件中列明，不会自动读取全部附件。</p>}
    {result.deferredSections?.length ? <p className="text-sm">部分声明保存在大产物中。请在内容选择中读取所需附件；附件保留原文，不自动推测声明字段。</p> : null}
    {options.length > 0 && !options.some((item) => item.format === "markdown") && <p className="text-sm">本次没有 Markdown 正文；可导出已确认的结构化内容，原值完整保留。</p>}
    {!options.length && <p role="status">尚无可复制或导出的确认正文，请查看执行证据。</p>}
    <div className="flex flex-wrap gap-2">
      <Button variant="outline" disabled={busy || unread || !selected.length} onClick={() => void deliver(true)}>复制所选正文</Button>
      <Button variant="outline" disabled={busy || unread || !selected.length} onClick={() => void deliver(false)}>导出 Markdown</Button>
    </div>
    {status && <p role="status">{status}</p>}
  </section>;
}
