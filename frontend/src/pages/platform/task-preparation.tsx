import { connectionName } from "./task-labels";
import type { Json } from "@/lib/types/workflow-platform";
import type { Preparation } from "@/lib/types/task-experience";
const issueMessages: Record<string, string> = {
  resource_unavailable: "需要补齐任务指定的服务连接。",
  plugin_unavailable: "所需服务尚未登记或启用，请先完成部署。",
  binding_invalid: "连接设置不完整，请检查服务、账户和业务范围。",
  model_not_found: "尚未连接模型服务。",
  resource_not_found: "尚未连接所需服务。",
};
function Issue({ code }: { code: string }) {
  return (
    <div className="text-sm">
      <p className="text-destructive">
        {issueMessages[code] ?? "连接准备尚未通过，请检查设置后重试。"}
      </p>
      <details>
        <summary>技术详情</summary>
        <code>{code}</code>
      </details>
    </div>
  );
}
export function SafeSettings({ value }: { value: Json }) {
  if (value === null) return <span>未设置</span>;
  if (Array.isArray(value))
    return (
      <ul className="flex flex-col gap-1">
        {value.map((item, i) => (
          <li key={i}>
            <SafeSettings value={item} />
          </li>
        ))}
      </ul>
    );
  if (typeof value === "object")
    return (
      <div className="flex flex-col gap-2">
        <dl className="grid grid-cols-1 gap-2 sm:grid-cols-[minmax(8rem,auto)_1fr]">
          {Object.entries(value).map(([key, item]) => (
              <div className="contents" key={key}>
                <dt className="text-muted-foreground break-all">
                  {key}
                </dt>
                <dd className="min-w-0 break-words">
                  <SafeSettings value={item} />
                </dd>
              </div>
            ))}
        </dl>
      </div>
    );
  return (
    <span>
      {typeof value === "boolean"
        ? value
          ? "开启"
          : "关闭"
        : String(value)}
    </span>
  );
}
const observationLabels = {
  not_observed: "尚无调用观测",
  succeeded: "最近调用成功",
  failed: "最近调用失败",
  unknown: "最近调用未确认",
};
export function TaskPreparation({ preparation }: { preparation: Preparation }) {
  return (
    <section
      className="flex flex-col gap-3 rounded-md border border-ui-separator bg-ui-surface-grouped p-4"
      aria-label="本次有效设置"
    >
      <h2 className="font-medium">本次有效设置</h2>
      <p className="text-sm">
        {preparation.ready
          ? "配置已就绪；开始时仍会校验，服务是否可用以实际执行结果为准。"
          : "尚需完成以下准备。填写的业务信息会保留。"}
      </p>
      {preparation.issues.map((issue) => (
        <Issue key={issue} code={issue} />
      ))}
      {preparation.changedBindings.length > 0 && (
        <div role="alert" className="flex flex-col gap-2">
          <strong>与上次相比，连接或业务范围已变化，请核对后确认开始。</strong>
          <p>
            {preparation.changedBindings.join("、")}
          </p>
          <details>
            <summary>上次使用的设置</summary>
            <SafeSettings value={preparation.previousBindings} />
          </details>
        </div>
      )}
      <ul className="flex flex-col gap-3">
        {preparation.requirements.map((requirement, i) => (
          <li key={`${requirement.id}-${i}`}>
            <p className="font-medium">
              {connectionName(requirement.name, requirement.id)} ·{" "}
              {requirement.configured ? "已有配置" : "缺少配置"}
            </p>
            <p className="text-sm text-muted-foreground">
              {requirement.hasCredentials ? "已保存凭据" : "未保存凭据"} ·
              {observationLabels[requirement.observation]}
              {requirement.observedAt &&
                ` · ${new Date(requirement.observedAt).toLocaleString()}`}
            </p>
            {requirement.issue && <Issue code={requirement.issue} />}
            <SafeSettings value={requirement.config} />
          </li>
        ))}
      </ul>
      <details>
        <summary className="cursor-pointer text-sm">
          更多有效设置（执行限制、预算和授权）
        </summary>
        <div className="pt-3 text-sm">
          <SafeSettings value={preparation.effectiveSettings} />
        </div>
      </details>
    </section>
  );
}
