import { ConsoleSection } from "@/components/shared/console-section";
import { InlineStatePanel } from "@/components/shared/inline-state-panel";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useModelUsage } from "@/hooks/use-model-usage";
import type { ModelUsage, ModelUsageSummary } from "@/lib/types/model-usage";
import type { Json } from "@/lib/types/workflow-platform";

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
        ["输入 token", count(usage.inputTokens)],
        ["输出 token", count(usage.outputTokens)],
        ["模型逻辑调用", count(usage.modelCalls)],
        ["模型累计耗时", duration(usage.durationMs)],
      ].map(([label, value]) => <div key={label} className="min-w-0">
        <dt className="text-xs text-muted-foreground">{label}</dt>
        <dd className="break-words text-sm font-medium tabular-nums">{value}</dd>
      </div>)}
    </dl>
    {usage.modelCalls === 0 ? <p className="text-xs text-muted-foreground">当前范围没有模型调用记录。</p> : <p className="text-xs text-muted-foreground">
      {usage.confirmedCalls} 次已确认成功，{usage.failedCalls} 次失败，{usage.unconfirmedCalls} 次未确认。
      {usage.usageMissingCalls > 0 && ` ${usage.usageMissingCalls} 次缺少完整用量；显示的 token 仅包含已报告部分，未知不是 0。`}
      {usage.durationKnownCalls < usage.modelCalls && " 未结束或缺少时间的调用不计入累计耗时。"}
    </p>}
    <p className="text-xs text-muted-foreground">
      网络尝试 {usage.networkAttempts} 次，其中失败 {usage.failedNetworkAttempts} 次、未确认 {usage.unconfirmedNetworkAttempts} 次。
      失败尝试未报告的消耗不包含在 token 中。
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
          <p className="break-all text-xs">{model.resourceId} · {model.modelId} · {model.apiStyle}</p>
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
  return <ConsoleSection title="模型用量" description="按模型逻辑调用统计已报告 token；今日按调用开始日期归属。此处不表示账户余额或供应商账单。" contentClassName="flex flex-col gap-4">
    {queries.map(({ title, query }) => query.isError ? <InlineStatePanel key={title} tone="warning" title={`${title}暂时无法读取`}>
      <Button variant="outline" size="sm" onClick={() => void query.refetch()}>重新读取用量</Button>
    </InlineStatePanel> : query.data ? <ModelUsageDetails key={title} title={title} data={query.data} /> : <div key={title} role="status" aria-label={`正在读取${title}`}><Skeleton className="h-16 w-full" /></div>)}
  </ConsoleSection>;
}

export function ModelBudgetSummary({ settings }: { settings: Json }) {
  if (!settings || typeof settings !== "object" || Array.isArray(settings)) return null;
  const agents = settings.agents;
  if (!agents || typeof agents !== "object" || Array.isArray(agents)) return null;
  const rows = Object.entries(agents).flatMap(([key, value]) => {
    if (!value || typeof value !== "object" || Array.isArray(value)) return [];
    const strategy = value.strategy;
    if (!strategy || typeof strategy !== "object" || Array.isArray(strategy) || strategy.kind !== "model") return [];
    const budget = value.budget;
    if (!budget || typeof budget !== "object" || Array.isArray(budget)) return [];
    return [{ key, budget }];
  });
  if (!rows.length) return null;
  return <section aria-label="模型预算" className="flex flex-col gap-2 text-sm">
    <h3 className="font-medium">模型预算</h3>
    <ul className="flex flex-col gap-2">
      {rows.map(({ key, budget }) => <li key={key} className="break-words">
        {key}：总 token {String(budget.maxTokens ?? "未设置")}；单次输出 {budget.maxOutputTokens === undefined ? "沿用剩余总预算" : `${budget.maxOutputTokens} token（同时受剩余总预算限制）`}；最多 {String(budget.maxModelRequests ?? "未设置")} 次请求；时限 {String(budget.deadlineSeconds ?? "未设置")} 秒。
      </li>)}
    </ul>
  </section>;
}
