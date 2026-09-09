import { Link, useParams, useSearchParams } from "react-router";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Button } from "@/components/ui/button";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { InlineStatePanel } from "@/components/shared/inline-state-panel";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { useRunResult } from "@/hooks/use-results";
import {
  usePlatformMutations,
} from "@/hooks/use-workflow-platform";
import { useTaskReuse } from "@/hooks/use-task-experience";
import type { RunResult } from "@/lib/types/result";
import { RequestError } from "./feedback";
import { resultStatusLabels, originLabels } from "./result-labels";
import { findArtifacts } from "./artifact-references";
import { runSearch } from "./result-navigation";
import { DeclaredResultSections } from "./result-sections";
import { ResultRepeat } from "./result-repeat";
import {
  ResultValue as Value,
  ResultAttachmentView as Attachment,
  ArtifactReading,
} from "./result-content";
export function ResultPage() {
  const { runId } = useParams();
  const query = useRunResult(runId);
  if (query.isPending) return <InventoryStatePanel title="正在加载结果…" />;
  if (!query.data)
    return (
      <RequestError error={query.error} retry={() => void query.refetch()} />
    );
  return <ResultContent key={query.data.runId} result={query.data} />;
}
function ResultContent({ result }: { result: RunResult }) {
  const [search] = useSearchParams();
  const primaryArtifact = result.attachments
    .filter((a) => a.kind === "artifact" && !a.evidenceId)
    .flatMap((a) => findArtifacts(a.reference))
    .find(
      ({ ref }) =>
        ref.mediaType.startsWith("text/") || ref.mediaType.includes("json"),
    )?.ref;
  const original = useTaskReuse(result.runId);
  const mutations = usePlatformMutations();
  const active = result.status === "queued" || result.status === "running";
  return (
    <InventoryPageShell
      pageContext={{
        title: result.title,
        description: `${originLabels[result.origin.kind]} · ${new Date(result.createdAt).toLocaleString()}`,
        status: (
          <ResourceStatusBadge
            label={resultStatusLabels[result.status] ?? result.status}
          />
        ),
        actions: (
          <div className="flex flex-wrap gap-2">
            <Button asChild variant="outline">
              <Link
                to={`/runs${search.get("history") ? `?${search.get("history")}` : ""}`}
              >
                全部结果
              </Link>
            </Button>
            {active && (
              <Button
                variant="outline"
                disabled={
                  !!result.cancelRequestedAt || mutations.cancel.isPending
                }
                onClick={() =>
                  void mutations.cancel
                    .mutateAsync(result.runId)
                    .catch(() => {})
                }
              >
                取消本次运行
              </Button>
            )}
          </div>
        ),
      }}
    >
      <RequestError error={mutations.cancel.error || original.error} />
      {result.cancelRequestedAt && (
        <InlineStatePanel
          title={
            active
              ? "已请求取消，正在等待执行停止"
              : result.status === "cancelled"
                ? "本次运行已取消"
                : "执行已结束"
          }
          description="已经完成的保存或其他外部操作仍会保留。"
        />
      )}
      {result.contentStatus === "unknown" && (
        <InlineStatePanel
          tone="warning"
          title="保存状态待核实"
          description="服务尚未确认是否保存成功。请先检查执行证据或目标位置，避免重复保存。"
        />
      )}
      {result.errorCode && (
        <InlineStatePanel
          tone="danger"
          title="本次任务未能完成"
          description="请查看下方缺失信息与技术详情，修复问题后再运行。"
        >
          <Button asChild variant="outline">
            <Link to={`/tasks/new?fromRun=${encodeURIComponent(result.runId)}`}>
              保留输入并检查连接
            </Link>
          </Button>
        </InlineStatePanel>
      )}
      {result.missing.length > 0 && (
        <InlineStatePanel tone="warning" title="资料不完整">
          <ul className="list-disc pl-5">
            {result.missing.map((item) => (
              <li key={item}>
                {item}
              </li>
            ))}
          </ul>
        </InlineStatePanel>
      )}
      {result.deferredSections?.length ? (
        <InlineStatePanel title="内容保存在执行产物">
          {result.deferredSections.join("、")}：请阅读或下载下方附件。
        </InlineStatePanel>
      ) : null}
      {result.executionIssues?.length ? (
        <InlineStatePanel tone="danger" title="执行未完成">
          {result.executionIssues.map((issue) => <p key={issue}>{issue}</p>)}
        </InlineStatePanel>
      ) : null}
      {result.skipped?.length ? (
        <InlineStatePanel title="已跳过的分支">{result.skipped.join("、")}</InlineStatePanel>
      ) : null}
      {result.sections?.length ? (
        <DeclaredResultSections sections={result.sections} search={search} />
      ) : result.body ? (
        <article
          aria-label="结果正文"
          className="min-w-0 overflow-x-auto rounded border border-border bg-card p-4 text-sm [&_h1]:mb-3 [&_h1]:text-xl [&_h2]:my-3 [&_h2]:text-lg [&_p]:my-2 [&_ul]:list-disc [&_ul]:pl-5"
        >
          <Markdown remarkPlugins={[remarkGfm]}>{result.body}</Markdown>
        </article>
      ) : result.receipt !== null ? (
        <section className="rounded border border-border bg-card p-4">
          <h2 className="mb-3 font-semibold">保存回执</h2>
          <Value value={result.receipt} />
        </section>
      ) : primaryArtifact ? (
        <section aria-label="结果正文">
          <ArtifactReading
            key={primaryArtifact.digest}
            digest={primaryArtifact.digest}
            mediaType={primaryArtifact.mediaType}
            initialOpen
          />
        </section>
      ) : (
        <InventoryStatePanel
          title={
            active
              ? result.status === "queued"
                ? "任务已接收，正在等待开始"
                : "正在处理，结果会自动更新"
              : "尚无可阅读的正文或保存回执"
          }
          description={
            result.contentStatus === "unknown"
              ? "保存状态仍需核实。"
              : "这里保留本次运行的真实状态和记录。"
          }
        />
      )}
      <section className="grid gap-4 border-y border-border py-4 sm:grid-cols-2">
        <div>
          <h2 className="mb-2 font-semibold">来源与时间</h2>
          <p className="text-sm">数据时间：{result.dataTime ?? "未提供"}</p>
          <p className="text-sm">
            完成时间：
            {result.finishedAt
              ? new Date(result.finishedAt).toLocaleString()
              : "尚未结束"}
          </p>
          {result.sources.length ? (
            result.sources.map((source, i) => <Value key={i} value={source} />)
          ) : (
            <p className="text-sm text-muted-foreground">未记录资料来源</p>
          )}
          {result.origin.sourceRunId && (
            <Link
              className="text-sm underline"
              to={`/runs/${encodeURIComponent(result.origin.sourceRunId)}`}
            >
              查看原始结果
            </Link>
          )}
          {result.origin.scheduleId && (
            <Link
              className="text-sm underline"
              to={`/scheduled-tasks/${encodeURIComponent(result.origin.scheduleId)}`}
            >
              查看重复安排
            </Link>
          )}
          {result.origin.scheduledAt && (
            <p className="text-sm">计划时间：{result.origin.scheduledAt}</p>
          )}
          {result.freshness.map((item, i) => (
            <Value key={i} value={item} />
          ))}
        </div>
        <div>
          <h2 className="mb-2 font-semibold">本次输入</h2>
          {original.data && <Value value={original.data.parameters} />}
        </div>
      </section>
      {result.attachments.length > 0 && (
        <section>
          <h2 className="font-semibold">附件与保存位置</h2>
          <ul>
            {result.attachments.map((attachment, i) => (
              <Attachment
                key={i}
                attachment={attachment}

              />
            ))}
          </ul>
        </section>
      )}
      <div className="flex flex-wrap gap-2">
        {result.unknownEvidenceIds.map((id) => (
          <Button key={id} asChild variant="outline">
            <Link to={`?${runSearch(search, { tab: "evidence", target: id })}`}>
              核实未确认的操作
            </Link>
          </Button>
        ))}
        <ResultRepeat result={result} original={original.data} />
        <Button asChild variant="outline">
          <Link to={`/tasks/new?fromRun=${encodeURIComponent(result.runId)}`}>
            修改输入后开始
          </Link>
        </Button>
        <Button asChild variant="outline">
          <Link
            to="/scheduled-tasks/new"
            state={{
              scheduleInput: original.data
                ? {
                    packageKey: original.data.packageKey,
                    workflowKey: original.data.workflowKey,
                    parameters: original.data.parameters,
                    name: result.title,
                  }
                : undefined,
            }}
          >
            设置重复执行
          </Link>
        </Button>
        <Button asChild variant="ghost">
          <Link to={`?${runSearch(search, { tab: "evidence" })}`}>
            技术详情与调用证据
          </Link>
        </Button>
      </div>
    </InventoryPageShell>
  );
}
