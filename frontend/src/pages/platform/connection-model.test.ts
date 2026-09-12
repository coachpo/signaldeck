import { expect, it } from "vitest";
import { prepareConnectionConfig } from "./connection-model";
it("normalizes a complete model address while retaining provider limits and unrelated saved settings", () => {
  const capabilities = { outputTokenLimitParameter: "max_tokens" };
  expect(prepareConnectionConfig("model", { name: "  本地分析  ", modelId: " glm-5.3-flash ", baseUrl: "http://192.168.1.222:8088/v1/chat/completions", apiStyle: "chat_completions", providerCapabilities: capabilities, timeoutSeconds: 120 })).toEqual({ name: "本地分析", modelId: "glm-5.3-flash", baseUrl: "http://192.168.1.222:8088/v1", apiStyle: "chat_completions", providerCapabilities: capabilities, timeoutSeconds: 120 });
});
it.each(["javascript:alert(1)", "https://secret:password@example.com/v1", "https://example.com/v1?key=secret", "not a url"])("rejects unsupported or credential-bearing service addresses: %s", (baseUrl) => {
  expect(() => prepareConnectionConfig("model", { name: "服务", modelId: "my-model", baseUrl })).toThrow("请填写完整的服务地址");
});
it("validates model names and execution limits before making a request", () => {
  expect(() => prepareConnectionConfig("model", { name: "服务", modelId: "", baseUrl: "https://example.com/v1" })).toThrow("请填写服务提供的模型名称");
  expect(() => prepareConnectionConfig("model", { name: "服务", modelId: "a", baseUrl: "https://example.com/v1", timeoutSeconds: 0 })).toThrow("最长等待时间");
});
it("preserves arbitrary business scope while checking meaningful service limits", () => {
  const config = { name: "范围", pluginId: "independent/service", scope: { collection: "raw-user-value", nested: { account: "chosen" } }, maxConcurrentCalls: 8, requestsPerSecond: 3.5 };
  expect(prepareConnectionConfig("tool", config)).toEqual(config);
  expect(() => prepareConnectionConfig("tool", { ...config, requestsPerSecond: 0 })).toThrow("每秒处理数量");
});
