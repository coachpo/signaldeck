import { ModelBudgetSummary } from "./model-usage-panel";
import { ModelObservationDetails } from "./execution-diagnostic";
import { usePlugins } from "@/hooks/use-workflow-platform";
import { pluginName } from "./connection-model";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
import type { Preparation } from "@/lib/types/task-experience";
const issueMessages: Record<string, string> = {
  resource_unavailable: "需要补齐任务使用的服务连接。",
  plugin_unavailable: "所需扩展服务尚未添加或启用，请先完成服务设置。",
  binding_invalid: "连接设置不完整，请检查服务、账户和业务范围。",
  model_not_found: "尚未连接模型服务。",
  resource_not_found: "尚未连接所需服务。",
};
function Issue({ code }: { code: string }) {
  return <p className="text-sm text-destructive">{issueMessages[code] ?? "连接准备尚未通过，请检查设置后重试。"}</p>;
}
function object(value: Json): JsonObject | null {
  return value && typeof value === "object" && !Array.isArray(value) ? value : null;
}
/** Only use this reader for business scope values, never platform configuration. */
export function SafeSettings({ value, schema }: { value: Json; schema?: JsonObject }) {
  if (value === null) return <span>未设置</span>;
  if (Array.isArray(value)) return <ul className="flex flex-col gap-1">{value.map((item, i) => <li key={i}><SafeSettings value={item} /></li>)}</ul>;
  if (typeof value === "object") return <dl className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(8rem,auto)_1fr]">{Object.entries(value).map(([key, item]) => {
    const properties = object(schema?.properties ?? null);
    const field = object(properties?.[key] ?? null);
    return <div className="contents" key={key}><dt className="break-all text-muted-foreground">{typeof field?.title === "string" ? field.title : key}</dt><dd className="min-w-0 break-words"><SafeSettings value={item} schema={field || undefined} /></dd></div>;
  })}</dl>;
  return <span>{typeof value === "boolean" ? value ? "开启" : "关闭" : String(value)}</span>;
}
export function ConnectionSummary({ config, schema }: { config: JsonObject; schema?: JsonObject }) {
  const scope = config.scope && object(config.scope);
  return <div className="flex flex-col gap-2 text-sm">
    {typeof config.modelId === "string" && <p>模型：{config.modelId}</p>}
    {typeof config.baseUrl === "string" && <p className="break-all">服务地址：{config.baseUrl}</p>}
    {typeof config.timeoutSeconds === "number" && <p>最长等待：{config.timeoutSeconds} 秒</p>}
    {scope && Object.keys(scope).length > 0 && <div><p className="mb-2 font-medium">业务范围与保存位置</p><SafeSettings value={scope} schema={schema} /></div>}
    {typeof config.maxConcurrentCalls === "number" && <p>最多同时处理 {config.maxConcurrentCalls} 项</p>}
    {typeof config.requestsPerSecond === "number" && <p>每秒最多处理 {config.requestsPerSecond} 次</p>}
  </div>;
}
const observationLabels = { not_observed: "尚未使用，是否可用待确认", succeeded: "最近使用成功", failed: "最近使用失败", unknown: "最近结果未确认" };
const changeLabels: Record<string, string> = { models: "模型服务", resources: "业务服务或使用范围", plugins: "扩展服务" };
function PreviousConnections({ bindings }: { bindings: JsonObject }) {
  const rows = ["models", "resources"].flatMap((kind) => {
    const entries = bindings[kind] && object(bindings[kind]);
    return entries ? Object.values(entries).flatMap((value) => { const config = object(value); return config ? [config] : []; }) : [];
  });
  return rows.length ? <details><summary className="cursor-pointer text-sm">上次使用的连接与范围</summary><div className="flex flex-col gap-3 pt-3">{rows.map((config, index) => <section key={index}><p className="text-sm font-medium">{typeof config.name === "string" && config.name ? config.name : `连接 ${index + 1}`}</p><ConnectionSummary config={config} /></section>)}</div></details> : null;
}
export function TaskPreparation({ preparation }: { preparation: Preparation }) {
  const plugins = usePlugins();
  return <section className="flex flex-col gap-3 rounded-md border border-ui-separator bg-ui-surface-grouped p-4" aria-label="本次有效设置">
    <h2 className="font-medium">开始前确认</h2>
    <p className="text-sm">{preparation.ready ? "配置已就绪；服务是否可用以实际执行结果为准。确认以下设置后即可开始。" : "尚需完成以下准备。填写的业务信息会保留。"}</p>
    {[...new Set(preparation.issues)].map((issue) => <Issue key={issue} code={issue} />)}
    {preparation.changedBindings.length > 0 && <div role="alert" className="flex flex-col gap-2">
      <strong>与上次相比，连接或业务范围已变化，请核对后确认开始。</strong>
      <p>{preparation.changedBindings.map((kind) => changeLabels[kind] ?? "服务设置").join("、")}</p>
      <PreviousConnections bindings={preparation.previousBindings} />
    </div>}
    <ul className="flex flex-col gap-3">{preparation.requirements.map((requirement, i) => {
      const plugin = plugins.data?.items.find((item) => item.pluginId === (requirement.kind === "plugin" ? requirement.id : requirement.config.pluginId));
      const name = requirement.name && requirement.name !== requirement.id ? requirement.name : requirement.kind === "model" ? "模型服务" : plugin ? pluginName(plugin.release) : requirement.kind === "plugin" ? "扩展服务" : "业务服务";
      return <li key={`${requirement.id}-${i}`}>
        <p className="font-medium">{name} · {requirement.configured ? "已有配置" : "需要连接"}</p>
        {requirement.kind !== "plugin" && <p className="text-sm text-muted-foreground">{requirement.hasCredentials ? "已保存密钥" : "未设置密钥"}</p>}
        {requirement.kind === "model" ? <ModelObservationDetails observation={requirement.modelObservation} /> : <p className="text-sm text-muted-foreground">{observationLabels[requirement.observation]}{requirement.observedAt && ` · ${new Date(requirement.observedAt).toLocaleString()}`}</p>}
        {requirement.issue && !preparation.issues.includes(requirement.issue) && <Issue code={requirement.issue} />}
        <ConnectionSummary config={requirement.config} schema={plugin?.release.configSchema} />
      </li>;
    })}</ul>
    <ModelBudgetSummary settings={preparation.effectiveSettings} />
    <div className="flex flex-col gap-1 text-sm">
      {typeof preparation.effectiveSettings.deadlineSeconds === "number" && <p>任务最长执行时间：{preparation.effectiveSettings.deadlineSeconds} 秒</p>}
      {typeof preparation.effectiveSettings.maxParallelNodes === "number" && <p>最多同时进行 {preparation.effectiveSettings.maxParallelNodes} 个步骤</p>}
      {preparation.effectiveSettings.failurePolicy && <p>步骤失败时：{preparation.effectiveSettings.failurePolicy === "fail_fast" ? "停止其余工作" : "继续能够独立完成的工作"}</p>}
    </div>
  </section>;
}
