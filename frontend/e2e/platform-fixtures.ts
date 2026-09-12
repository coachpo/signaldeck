import { expect, type APIRequestContext } from "@playwright/test";
import { stringify } from "yaml";
export const apiBase = `http://127.0.0.1:${process.env.SIGNALDECK_E2E_BACKEND_PORT ?? "8001"}/api`;
export function packageSource(key: string, model: string) {
  const schema = {
    type: "object",
    properties: { summary: { type: "string" } },
    required: ["summary"],
  };
  return stringify(
    {
      apiVersion: "signaldeck.workflowPackage/v2",
      metadata: { key, name: `Package ${key}` },
      agents: {
        analyst: {
          name: "Reusable analyst",
          inputSchema: schema,
          outputSchema: schema,
          strategy: {
            kind: "model",
            modelRef: model,
            prompt: "Return a brief summary using the required output schema.",
          },
          tools: [],
          resources: [],
        },
      },
      workflows: {
        main: {
          name: "Main workflow",
          inputSchema: schema,
          outputSchema: schema,
          nodes: {
            first: { uses: "analyst", inputMapping: { ref: "workflow.input" } },
            second: {
              uses: "analyst",
              dependsOn: ["first"],
              inputMapping: { ref: "nodes.first.output" },
              condition: {
                op: "exists",
                args: [{ ref: "nodes.first.output.summary" }],
              },
            },
          },
          outputMapping: { ref: "nodes.second.output" },
        },
      },
    },
    { aliasDuplicateObjects: false },
  );
}
export async function seed(request: APIRequestContext) {
  const key = `e2e-${crypto.randomUUID().slice(0, 8)}`,
    model = `${key}-model`;
  const response = await request.post(`${apiBase}/resources`, {
    data: {
      resourceId: model,
      kind: "model",
      config: {
        name: "Fake E2E model",
        baseUrl:
          process.env.SIGNALDECK_FAKE_PROVIDER_BASE_URL ??
          `http://127.0.0.1:${process.env.SIGNALDECK_FAKE_PROVIDER_PORT ?? "18081"}/v1`,
        modelId: "fake-e2e-model",
        apiStyle: "chat_completions",
        timeoutSeconds: 30,
      },
      credentials: { apiKey: "fake-local-key" },
    },
  });
  expect(response.ok(), await response.text()).toBeTruthy();
  const source = packageSource(key, model);
  const saved = await request.post(`${apiBase}/workflow-packages`, {
    data: { manifestSource: source },
  });
  expect(saved.ok(), await saved.text()).toBeTruthy();
  return { key, model, source, pkg: await saved.json() };
}
