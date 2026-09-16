import type { Json } from "@/lib/types/workflow-platform";
const labels = [
  ["maxTokens", "累计模型用量"], ["maxOutputTokens", "单次输出"],
  ["maxModelRequests", "模型处理次数"], ["maxToolCalls", "服务操作次数"],
  ["deadlineSeconds", "最长执行时间"], ["maxParallelTools", "同时执行的操作数"],
] as const;
function object(value: Json | undefined) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : undefined;
}
function formatted(key: string, value: Json | undefined) {
  if (value === "unlimited") return "不设限";
  if (value === "provider_default") return "由模型服务决定";
  if (value === "auto" || (key === "maxOutputTokens" && value === undefined)) return "按剩余额度";
  if (typeof value !== "number") return "未记录";
  return `${value.toLocaleString()}${key === "deadlineSeconds" ? " 秒" : ""}`;
}
export function ModelBudgetSummary({ settings, frozen = false }: { settings: Json; frozen?: boolean }) {
  const agents = object(object(settings)?.agents);
  if (!agents) return null;
  const rows = Object.entries(agents).flatMap(([key, raw]) => {
    const value = object(raw);
    const budget = object(value?.budget);
    return budget ? [{ key, budget, name: typeof value?.name === "string" ? value.name : undefined, sources: object(value?.budgetSources) }] : [];
  });
  if (!rows.length) return null;
  return <section aria-label="模型使用限制" className="flex flex-col gap-3 text-sm">
    <h3 className="font-medium">{frozen ? "本次冻结的用量与时间限制" : "用量与时间限制"}</h3>
    <p className="text-xs text-muted-foreground">分别用于每次助手执行。累计用量在响应后核验，单次回复可能超过停止线。</p>
    {rows.map(({ key, name, budget, sources }, index) => <div key={key} className="flex flex-col gap-2">
      <h4 className="font-medium">{name || `助手 ${index + 1}`}</h4>
      <dl className="grid gap-2 sm:grid-cols-2">{labels.map(([field, label]) => <div key={field}>
        <dt className="text-xs text-muted-foreground">{label}</dt>
        <dd>{formatted(field, budget[field])}{sources?.[field] && <span className="text-xs text-muted-foreground"> · {sources[field] === "task" ? "本次设置" : sources[field] === "workflow" ? "工作流默认" : "平台默认"}</span>}</dd>
      </div>)}</dl>
    </div>)}
  </section>;
}
