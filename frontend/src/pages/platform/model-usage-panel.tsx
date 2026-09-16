import { ConsoleSection } from "@/components/shared/console-section";
import { InlineStatePanel } from "@/components/shared/inline-state-panel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useModelUsage } from "@/hooks/use-model-usage";
import type { ModelUsage, ModelUsageSummary } from "@/lib/types/model-usage";
export { ModelBudgetSummary } from "./budget-summary";

function count(value: number | null) {
  return value === null ? "未知" : value.toLocaleString();
}
function duration(value: number | null) {
  return value === null ? "未知" : `${(value / 1000).toLocaleString(undefined, { maximumFractionDigits: 2 })} 秒`;
}
function UsageNumbers({ usage }: { usage: ModelUsageSummary }) {
  return <div className="flex flex-col gap-2">
    <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
      {[
        ["输入用量", count(usage.inputTokens)],
        ["输出用量", count(usage.outputTokens)],
        ["模型处理次数", count(usage.modelCalls)],
        ["累计处理耗时", duration(usage.durationMs)],
      ].map(([label, value]) => <div key={label} className="min-w-0">
        <dt className="text-xs text-muted-foreground">{label}</dt>
        <dd className="break-words text-sm font-medium tabular-nums">{value}</dd>
      </div>)}
    </dl>
    {usage.modelCalls === 0 ? <p className="text-xs text-muted-foreground">当前范围没有模型调用记录。</p> : <p className="text-xs text-muted-foreground">
      {usage.confirmedCalls} 次已确认成功，{usage.failedCalls} 次失败，{usage.unconfirmedCalls} 次未确认。
      {usage.usageMissingCalls > 0 && ` ${usage.usageMissingCalls} 次缺少完整用量；显示的用量仅包含已报告部分，未知不是 0。`}
      {usage.durationKnownCalls < usage.modelCalls && " 未结束或缺少时间的调用不计入累计耗时。"}
    </p>}
    <p className="text-xs text-muted-foreground">
      联系服务 {usage.networkAttempts} 次，其中失败 {usage.failedNetworkAttempts} 次、未确认 {usage.unconfirmedNetworkAttempts} 次。
      失败尝试未报告的消耗不包含在用量中。
    </p>
  </div>;
}

export function ModelUsageDetails({ title, data }: { title: string; data: ModelUsage }) {
  return <section aria-label={title} className="flex min-w-0 flex-col gap-3">
    <h3 className="text-sm font-medium">{title}</h3>
    <UsageNumbers usage={data.summary} />
    {data.runId && <p className="text-xs text-muted-foreground">本次运行耗时：{duration(data.runDurationMs)}</p>}
    {data.models.length > 0 && <details>
      <summary className="cursor-pointer text-sm">按模型查看用量</summary>
      <ul className="flex flex-col gap-4 pt-3">
        {data.models.map((model) => <li key={`${model.resourceId}:${model.modelId}:${model.apiStyle}`} className="flex flex-col gap-2">
          <p className="break-all text-xs">模型：{model.modelId}</p>
          <UsageNumbers usage={model.summary} />
        </li>)}
      </ul>
    </details>}
  </section>;
}

export function ModelUsagePanel({ runId }: { runId?: string }) {
  const { run, day, selectedDay } = useModelUsage(runId);
  const queries = [
    ...(runId ? [{ title: "本次模型用量", query: run }] : []),
    { title: `今日模型用量 · ${selectedDay.date} · ${selectedDay.timezone}`, query: day },
  ];
  return <ConsoleSection title="模型用量" description="用量按服务报告的计量单位显示；今日按处理开始时间统计。不表示账户余额或最终账单。" contentClassName="flex flex-col gap-4">
    {queries.map(({ title, query }) => query.isError ? <InlineStatePanel key={title} tone="warning" title={`${title}暂时无法读取`}>
      <Button variant="outline" size="sm" onClick={() => void query.refetch()}>重新读取用量</Button>
    </InlineStatePanel> : query.data ? <ModelUsageDetails key={title} title={title} data={query.data} /> : <div key={title} role="status" aria-label={`正在读取${title}`}><Skeleton className="h-16 w-full" /></div>)}
  </ConsoleSection>;
}
