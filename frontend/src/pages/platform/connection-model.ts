import type { JsonObject, PluginRelease } from "@/lib/types/workflow-platform";

export function pluginName(release?: PluginRelease) {
  return typeof release?.configSchema?.title === "string" && release.configSchema.title.trim()
    ? release.configSchema.title : "扩展服务";
}
export function capabilityName(tool: JsonObject, index: number) {
  const schema = tool.inputSchema;
  return schema && typeof schema === "object" && !Array.isArray(schema) && typeof schema.title === "string"
    ? schema.title : `${tool.effect === "write" ? "保存" : "读取"}能力 ${index + 1}`;
}
export function newConnectionConfig(kind: "model" | "tool", name = ""): JsonObject {
  return kind === "model"
    ? { name, baseUrl: "", modelId: "", apiStyle: "chat_completions", timeoutSeconds: 60 }
    : { name, pluginId: "", scope: {}, maxConcurrentCalls: 4, requestsPerSecond: 10 };
}
export function prepareConnectionConfig(kind: "model" | "tool", config: JsonObject): JsonObject {
  if (typeof config.name !== "string" || !config.name.trim()) throw new Error("请为连接填写一个便于辨认的名称。");
  if (kind === "tool") {
    if (!config.pluginId) throw new Error("请选择要连接的服务。");
    if (!config.scope || typeof config.scope !== "object" || Array.isArray(config.scope)) throw new Error("请按项目填写业务范围与保存位置。");
    if (config.maxConcurrentCalls !== undefined && (!Number.isInteger(config.maxConcurrentCalls) || Number(config.maxConcurrentCalls) < 1 || Number(config.maxConcurrentCalls) > 1000))
      throw new Error("同时处理数量应在 1 到 1000 之间。");
    if (config.requestsPerSecond !== undefined && (Number(config.requestsPerSecond) <= 0 || Number(config.requestsPerSecond) > 10000))
      throw new Error("每秒处理数量应大于 0 且不超过 10000。");
    return config;
  }
  if (typeof config.modelId !== "string" || !config.modelId.trim()) throw new Error("请填写服务提供的模型名称。");
  let address: URL;
  try {
    address = new URL(String(config.baseUrl));
    if (!["http:", "https:"].includes(address.protocol) || address.username || address.password || address.search || address.hash) throw new Error();
  } catch { throw new Error("请填写完整的服务地址，例如 http://localhost:11434/v1；密钥请填在服务密钥中。"); }
  const timeout = config.timeoutSeconds;
  if (timeout !== undefined && (!Number.isInteger(timeout) || Number(timeout) < 1 || Number(timeout) > 3600))
    throw new Error("最长等待时间应为 1 到 3600 秒。");
  return { ...config, name: config.name.trim(), modelId: config.modelId.trim(), baseUrl: address.toString().replace(/\/(chat\/completions|responses)\/?$/, "").replace(/\/$/, "") };
}
