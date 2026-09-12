import { ApiRequestError } from "./api-client";

type ErrorNotice = { title: string; description: string };

const knownErrors: Record<string, ErrorNotice> = {
  draft_conflict: { title: "草稿已在其他窗口更新", description: "本页内容仍然保留。可以另存一份，或恢复已保存的草稿。" },
  draft_pending: { title: "任务是否开始仍需确认", description: "请返回任务草稿重试确认；确认前保留当前输入，避免重复执行。" },
  credential_input: { title: "请在服务连接中填写密钥", description: "任务输入仍然保留。请把登录信息移到连接设置，再保存或开始任务。" },
  binding_changed: { title: "本次使用的服务设置已变化", description: "请重新核对服务、保存位置和使用范围，再确认开始。输入已保留。" },
  resource_unavailable: { title: "任务需要的服务尚未连接", description: "请补齐下方服务连接，再重新核对。输入已保留。" },
  plugin_unavailable: { title: "任务需要的服务尚未启用", description: "请在服务管理中连接或启用对应服务，再回来继续。" },
  draft_definition_missing: { title: "此草稿对应的任务已不可用", description: "请保留草稿内容，返回任务列表选择可用任务。" },
  draft_source_mismatch: { title: "此草稿与原结果的任务不一致", description: "请返回原结果，使用“修改输入后开始”重新打开。原结果保持不变。" },
};

/** Transport and provider messages are diagnostic data, never product copy. */
export function userFacingError(error: unknown): ErrorNotice {
  if (error instanceof ApiRequestError) {
    if (knownErrors[error.code]) return knownErrors[error.code];
    if (error.status === 401 || error.status === 403)
      return { title: "暂时无法访问", description: "请检查访问凭据或服务连接，再重试。当前内容仍然保留。" };
    if (error.status === 404)
      return { title: "暂时找不到这项内容", description: "内容可能已被移除。可以重新加载，或返回列表查看现有内容。" };
    if (error.status === 409)
      return { title: "内容或设置已变化", description: "本页修改仍然保留。请核对最新内容后重试，避免覆盖其他窗口的修改。" };
    if (error.status === 400 || error.status === 422)
      return { title: "有些内容需要调整", description: "请检查必填信息、输入格式和所选服务，然后重试。当前内容仍然保留。" };
    if (error.status === 429)
      return { title: "服务目前较忙", description: "请稍后重试。若刚刚开始任务，请先查看结果或待确认草稿。" };
  }
  return { title: "暂时未能完成操作", description: "请检查连接后重试。若刚刚开始任务或保存内容，请先查看结果或待确认草稿，避免重复操作。" };
}
