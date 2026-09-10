import { Link } from "react-router";
import type { ModelErrorCategory, ModelObservation } from "@/lib/types/workflow-platform";

const outputLimitGuidance = "模型服务返回的输出超过本次上限，已停止该 Agent 的后续调用。已发生的用量仍保留；请核对连接的输出上限参数与供应商支持情况后再运行。";
const modelGuidance: Record<ModelErrorCategory, string> = {
  quota: "模型服务额度不足。请检查供应商账户余额或使用额度，恢复额度后再运行。",
  authentication: "模型服务认证失败。请检查连接中保存的凭据及账户访问权限。",
  rate_limit: "模型服务限制了请求频率。请稍后再运行，或检查供应商的速率限制。",
  model: "请求的模型不可用。请核对连接中的模型名称和账户可用模型。",
  input: "模型服务不接受本次输入。请检查输入长度、格式和模型支持的请求设置。",
  output_limit: outputLimitGuidance,
  unknown: "模型调用失败，具体原因未知。请查看调用证据并核对供应商状态。",
};
const codeGuidance: Record<string, string> = {
  model_output_limit_exceeded: outputLimitGuidance,
  package_not_found: "找不到任务定义。请检查安排使用的任务是否仍存在，并重新选择有效任务。",
  workflow_not_found: "找不到工作流。请检查安排中的任务选择。",
  resource_not_found: "缺少所需服务连接。请补齐连接后再运行。",
  model_not_found: "缺少模型连接。请在设置中补齐模型连接。",
  resource_unavailable: "所需服务连接不可用。请检查连接配置和服务状态。",
  binding_invalid: "连接设置不完整。请检查服务、账户和业务范围。",
  plugin_unavailable: "所需服务尚未登记或启用。请检查服务部署和启用状态。",
};
export function ExecutionDiagnostic({ code, category }: {
  code: string; category?: ModelErrorCategory | null;
}) {
  const message = codeGuidance[code] ?? (category ? modelGuidance[category] : code === "model_http_error"
    ? modelGuidance.unknown : undefined);
  return <div className="flex min-w-0 flex-col gap-2 text-sm">
    <p>{message ?? "执行失败，具体原因未知。请查看技术证据，核对任务配置与服务状态后再运行。"}</p>
    <details>
      <summary className="cursor-pointer">原始错误码</summary>
      <code className="break-all">{code}</code>
    </details>
  </div>;
}
const labels = {
  not_observed: "当前连接配置尚无调用观测",
  succeeded: "最近调用成功",
  failed: "最近调用失败",
  unknown: "最近调用未确认",
};
export function ModelObservationDetails({ observation }: { observation?: ModelObservation | null }) {
  return <div className="flex min-w-0 flex-col gap-2 text-sm">
    <p className="text-muted-foreground">
      {labels[observation?.status ?? "not_observed"]}
      {observation?.observedAt && ` · ${new Date(observation.observedAt).toLocaleString()}`}
    </p>
    <p className="text-muted-foreground">仅反映当前配置与凭据版本的已记录调用，不代表实时在线状态。</p>
    {observation?.errorCode && <ExecutionDiagnostic code={observation.errorCode} category={observation.errorCategory} />}
    {observation?.status === "unknown" && <p>调用结果未确认，请先查看证据再决定是否重试。</p>}
    {observation?.runId && <Link className="underline" to={`/runs/${encodeURIComponent(observation.runId)}?${new URLSearchParams({ tab: "evidence", ...(observation.evidenceId ? { target: observation.evidenceId } : {}) })}`}>
      查看最近调用证据
    </Link>}
  </div>;
}
