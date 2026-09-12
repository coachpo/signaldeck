import { expect, type APIRequestContext } from "@playwright/test";
import { apiBase } from "./platform-fixtures";

export async function connectTaskServices(request: APIRequestContext, model = true) {
  for (const [kind, defaultPort] of [["NOTES", "18082"], ["FINANCE", "18083"], ["ORACLE", "18084"]]) {
    const port = process.env[`SIGNALDECK_E2E_${kind}_PORT`] ?? defaultPort;
    const release = await request.get(`http://127.0.0.1:${port}/release`);
    expect(release.ok(), await release.text()).toBeTruthy();
    const installed = await request.post(`${apiBase}/plugins`, { data: { release: await release.json(), enabled: true } });
    expect(installed.ok(), await installed.text()).toBeTruthy();
  }
  for (const [resourceId, pluginId, scope] of [
    ["notes-workspace", "example/notes", { collection: "research" }],
    ["finance-market-data", "signaldeck/finance", { allowedSymbols: ["MSFT", "AAPL"] }],
  ] as const) {
    const saved = await request.post(`${apiBase}/resources`, { data: {resourceId, kind: "tool", config: {pluginId, scope}} });
    expect(saved.ok(), await saved.text()).toBeTruthy();
  }
  if (model) await connectResearchModel(request);
}

export async function connectResearchModel(request: APIRequestContext) {
  const saved = await request.post(`${apiBase}/resources`, { data: {
    resourceId: "research-model", kind: "model",
    config: {name: "Controlled local research", baseUrl: process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ?? `http://127.0.0.1:${process.env.SIGNALDECK_FAKE_PROVIDER_PORT ?? "18081"}/v1`, modelId: "fake-e2e-oracle-tools", apiStyle: "chat_completions", timeoutSeconds: 30},
    credentials: {apiKey: "fake-local-key"},
  }});
  expect(saved.ok(), await saved.text()).toBeTruthy();
}
