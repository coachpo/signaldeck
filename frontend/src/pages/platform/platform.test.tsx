import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PackageStructure } from "./package-structure";
import {
  parseDefinition,
  initialPackageSource,
  updateSource,
} from "@/lib/platform-authoring/package-source";
import { PackageEditorPage } from "./packages";
import { DependencyGraph } from "./dependency-graph";
import { ArtifactValue, EvidenceTree } from "./evidence";
import { RunPage } from "./runs";
import { ResourcesPage } from "./resources";
import { PluginsPage } from "./plugins";
import { LaunchInputs } from "./launch-inputs";
import { findArtifacts } from "./artifact-references";
import { safePluginPageUrl } from "./plugin-links";
import { packageFixture, runFixture } from "./fixtures";
import type { ReactNode } from "react";
function renderPage(element: ReactNode, path = "/") {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const router = createMemoryRouter(
    [
      { path: "*", element },
      { path: "/runs/:runId", element },
      { path: "/workflow-packages/:packageId", element },
    ],
    { initialEntries: [path] },
  );
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    ),
  };
}
function response(data: unknown) {
  return new Response(JSON.stringify(data), {
    headers: { "content-type": "application/json" },
  });
}
afterEach(() => vi.unstubAllGlobals());
describe("frozen definition editing", () => {
  it("edits the same document without erasing nodes, comments or constraints", () => {
    const source = "# operator note\n" + initialPackageSource;
    const onChange = vi.fn();
    render(<PackageStructure source={source} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("工作流集名称"), { target: { value: "Changed" } });
    const next = onChange.mock.calls[0][0] as string;
    expect(next).toContain("# operator note");
    expect(parseDefinition(next).metadata.name).toBe("Changed");
    expect(parseDefinition(next).workflows).toEqual(parseDefinition(source).workflows);
  });
  it("keeps unreadable imports without silently repairing or exposing source errors", () => {
    render(<PackageStructure source="agents: [" onChange={vi.fn()} />);
    expect(screen.getByText("无法读取这份工作流")).toBeVisible();
    expect(screen.queryByLabelText("工作流集名称")).not.toBeInTheDocument();
    expect(screen.queryByText(/YAML|line|agents/)).not.toBeInTheDocument();
  });
  it("adds a workflow through controls without replacing the other sections", () => {
    const onChange = vi.fn();
    render(<PackageStructure source={initialPackageSource} onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "添加任务流程" }));
    const result = parseDefinition(onChange.mock.calls[0][0]);
    expect(Object.keys(result.workflows)).toHaveLength(2);
    expect(result.agents).toEqual(parseDefinition(initialPackageSource).agents);
    expect(result.workflows.main).toEqual(parseDefinition(initialPackageSource).workflows.main);
  });
  it("uses the saved document rather than stale summary metadata", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ ...packageFixture, name: "Summary is stale" })));
    renderPage(<PackageEditorPage />, "/workflow-packages/example");
    expect(await screen.findByLabelText("工作流集名称")).toHaveValue(parseDefinition(packageFixture.source).metadata.name);
    expect(screen.queryByLabelText("Workflow Package YAML")).not.toBeInTheDocument();
  });
  it("names authoring services from declared titles and safe effect labels without protocol descriptions", async () => {
    const description = "includeDerived and sourceNoteIds are required in the tool protocol.";
    const tools = [
      { toolId: "example/services/search", effect: "read", description, inputSchema: { type: "object", title: "搜索我的资料" } },
      { toolId: "example/services/read", effect: "read", description, inputSchema: { type: "object", title: " " } },
      { toolId: "example/services/save", effect: "write", description, inputSchema: { type: "object" } },
      { toolId: "example/services/other", description, inputSchema: { type: "object" } },
    ];
    vi.stubGlobal("fetch", vi.fn().mockImplementation((input: string) => {
      if (String(input).endsWith("/plugins")) return Promise.resolve(response({ items: [{ enabled: true, release: { tools } }] }));
      if (String(input).endsWith("/resources")) return Promise.resolve(response({ items: [] }));
      return Promise.resolve(response(packageFixture));
    }));
    renderPage(<PackageEditorPage />, "/workflow-packages/tool-label-check");
    fireEvent.click(await screen.findByRole("button", { name: "Assistant" }));
    for (const name of ["搜索我的资料", "读取资料 2", "保存内容 3", "服务操作 4"])
      expect(await screen.findByRole("checkbox", { name })).toBeVisible();
    expect(screen.queryByText(/includeDerived|sourceNoteIds|example\/services/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("combobox", { name: "完成方式" }));
    fireEvent.click(screen.getByRole("option", { name: "直接执行服务操作" }));
    fireEvent.click(screen.getByRole("combobox", { name: "执行的服务操作" }));
    expect(screen.getByRole("option", { name: "搜索我的资料" })).toBeVisible();
    expect(screen.getByRole("option", { name: "保存内容 3" })).toBeVisible();
    expect(screen.queryByText(/includeDerived|sourceNoteIds/)).not.toBeInTheDocument();
  });
  it("blocks editing when reading the saved workflow fails and offers recovery", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({ code: "unavailable", message: "Read unavailable", details: [] }), { status: 503, headers: { "content-type": "application/json" } })));
    renderPage(<PackageEditorPage />, "/workflow-packages/example");
    expect(await screen.findByRole("button", { name: "重试" })).toBeVisible();
    expect(screen.queryByLabelText("工作流集名称")).not.toBeInTheDocument();
    expect(screen.queryByText("Read unavailable")).not.toBeInTheDocument();
  });
});
describe("execution inspection", () => {
  it("shows all merged dependency sources and real terminal reasons", () => {
    render(
      <DependencyGraph
        plan={{
          workflowKey: "main",
          nodeOrder: ["first", "last"],
          dependencies: { first: [], last: ["first"] },
          edges: [
            {
              source: "first",
              target: "last",
              sources: ["control", "input", "condition"],
              paths: ["nodes.last.dependsOn", "nodes.last.condition"],
            },
          ],
        }}
        evidence={[
          {
            ...runFixture.evidence[0],
            nodeId: "last",
            status: "blocked",
            errorCode: "upstream_failed",
          },
        ]}
      />,
    );
    expect(screen.getByText("步骤 1 → 步骤 2")).toBeVisible();
    for (const source of ["等待完成", "使用结果", "根据结果判断"])
      expect(screen.getByText(source)).toBeVisible();
    expect(screen.getByText("前置步骤未完成")).toBeVisible();
    expect(screen.queryByText("upstream_failed")).not.toBeInTheDocument();
  });
  it("renders invocation ownership separately from the dependency graph", () => {
    renderPage(<EvidenceTree evidence={runFixture.evidence} />);
    const tree = screen.getByLabelText("步骤与服务操作");
    const node = within(tree)
      .getByRole("link", { name: "任务步骤 · 第 1 次" })
      .closest("li")!;
    expect(
      within(node).getByRole("link", { name: "服务操作 1 · 第 1 次" }),
    ).toHaveAttribute("href", "/?tab=evidence&target=tool-1");
    expect(within(node).getByText("结果未确认")).toBeVisible();
    expect(within(node).queryByText("operation-stable")).not.toBeInTheDocument();
  });
  it("validates evidence deep links against the loaded run", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(runFixture)));
    renderPage(<RunPage />, "/runs/run-1?tab=evidence&target=missing");
    expect(
      await screen.findByText("本次任务中找不到所选操作"),
    ).toBeVisible();
  });
  it("inspects a planned node without inventing missing input or reporting an invalid evidence link", async () => {
    const run = {
      ...runFixture,
      spec: {
        ...runFixture.spec,
        plan: {
          workflowKey: "main",
          nodeOrder: ["answer", "future"],
          dependencies: { answer: [], future: ["answer"] },
          edges: [
            {
              source: "answer",
              target: "future",
              sources: ["control"],
              paths: ["$.workflows.main.nodes.future.dependsOn.0"],
            },
          ],
        },
      },
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(async () => response(run)),
    );
    renderPage(<RunPage />, "/runs/run-1?tab=graph");
    fireEvent.click(await screen.findByRole("button", { name: "步骤 2" }));
    expect(
      await screen.findByText("步骤 2：尚未开始处理"),
    ).toBeVisible();
    expect(
      screen.queryByText("本次任务中找不到所选操作"),
    ).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Input JSON")).not.toBeInTheDocument();
  });
  it("loads CAS text only on demand and clears an unrelated artifact selection", async () => {
    const ref = {
      digest: `sha256:${"a".repeat(64)}`,
      sizeBytes: 42,
      mediaType: "application/json",
    };
    const fetcher = vi
      .fn()
      .mockResolvedValue(new Response('{"amount":"99999999999999999.01"}'));
    vi.stubGlobal("fetch", fetcher);
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const { rerender } = render(
      <QueryClientProvider client={client}>
        <ArtifactValue label="Output" value={ref} />
      </QueryClientProvider>,
    );
    expect(fetcher).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "阅读附件正文" }));
    expect(await screen.findByText("99999999999999999.01")).toBeVisible();
    expect(screen.queryByText(ref.digest)).not.toBeInTheDocument();
    rerender(
      <QueryClientProvider client={client}>
        <ArtifactValue label="Output" value={{ other: "value" }} />
      </QueryClientProvider>,
    );
    expect(
      screen.queryByText("99999999999999999.01"),
    ).not.toBeInTheDocument();
  });
  it("discovers nested CAS references without converting ordinary money strings", () => {
    const ref = {
      digest: `sha256:${"a".repeat(64)}`,
      sizeBytes: 100,
      mediaType: "application/json",
    };
    expect(
      findArtifacts({ amount: "999999999999999999.01", rows: [ref] }),
    ).toEqual([{ path: "$.rows.0", ref }]);
    expect(
      findArtifacts({
        digest: "some-key",
        sizeBytes: 0,
        mediaType: "text/plain",
      }),
    ).toEqual([]);
  });
});
describe("resources and independent plugins", () => {
  it("does not refill saved credential values and clears newly submitted credentials", async () => {
    const resource = {
      resourceId: "model",
      kind: "model",
      config: { name: "我的模型", baseUrl: "http://localhost:18081/v1", modelId: "local", apiStyle: "chat_completions" },
      hasCredentials: true,
      credentialRevision: "revision-1",
    };
    const fetcher = vi.fn(async (input: unknown, init?: RequestInit) =>
      response(init?.method === "POST" ? resource : { items: String(input).includes("plugins") ? [] : [resource] }),
    );
    vi.stubGlobal("fetch", fetcher);
    renderPage(<ResourcesPage />);
    fireEvent.click(await screen.findByRole("button", { name: "编辑 我的模型" }));
    expect(screen.getByLabelText("服务密钥")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("服务密钥"), {
      target: { value: "new-private-value" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
    await waitFor(() =>
      expect(screen.getByLabelText("服务密钥")).toHaveValue(""),
    );
    const write = fetcher.mock.calls.find(
      ([, init]) => init?.method === "POST",
    )!;
    expect(JSON.parse(write[1]!.body as string).credentials).toEqual({
      apiKey: "new-private-value",
    });
    expect(document.body.textContent).not.toContain("new-private-value");
  });
  it("does not echo credential values from rejected saves into diagnostics", async () => {
    vi.stubGlobal("fetch", vi.fn(async (_input: unknown, init?: RequestInit) => init?.method === "POST"
      ? new Response(JSON.stringify({ code: "resource_invalid", message: "rejected private-secret", details: [] }), { status: 422, headers: { "content-type": "application/json" } })
      : response({ items: [] })));
    renderPage(<ResourcesPage />);
    fireEvent.click(screen.getByRole("button", { name: "添加连接" }));
    fireEvent.change(screen.getByLabelText("连接名称"), { target: { value: "另一模型" } });
    fireEvent.change(screen.getByLabelText("服务地址"), { target: { value: "http://localhost:18081/v1" } });
    fireEvent.change(screen.getByLabelText("模型名称"), { target: { value: "local" } });
    fireEvent.change(screen.getByLabelText("服务密钥"), { target: { value: "private-secret" } });
    fireEvent.click(screen.getByRole("button", { name: "保存连接" }));
    expect(await screen.findByText("有些内容需要调整")).toBeVisible();
    expect(screen.getByLabelText("服务密钥")).toHaveValue("private-secret");
    for (const alert of screen.getAllByRole("alert"))
      expect(alert).not.toHaveTextContent("private-secret");
  });
  it("takes business page links from enabled plugin releases and rejects executable URLs", async () => {
    const release = {
      pluginId: "external/weather",
      releaseId: "2",
      protocolVersion: "v1",
      artifactDigest: "sha256:a",
      pageUrl: "https://weather.example/workspace",
      configSchema: { type: "object", title: "天气服务" },
      tools: [],
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          items: [
            {
              pluginId: release.pluginId,
              enabled: true,
              health: {
                status: "not_observed",
                observedAt: null,
                errorCode: null,
                runId: null,
                operationId: null,
                evidenceId: null,
              },
              release,
            },
          ],
        }),
      ),
    );
    renderPage(<PluginsPage />);
    expect(
      await screen.findByRole("link", { name: "打开服务" }),
    ).toHaveAttribute("href", "https://weather.example/workspace");
    expect(screen.getByText("天气服务")).toBeVisible();
    expect(document.body.textContent).not.toContain("external/weather");
    expect(safePluginPageUrl("javascript:alert(1)")).toBeNull();
    expect(safePluginPageUrl("data:text/html,x")).toBeNull();
  });
  it("edits exact string inputs without adding omitted optional values", () => {
    const change = vi.fn(), dirty = vi.fn();
    render(<LaunchInputs schema={{ type: "object", properties: { amount: { type: "string" }, optional: { type: "string" } }, required: ["amount"] }} value={{ amount: "1.00" }} onChange={change} onDirtyChange={dirty} />);
    fireEvent.change(screen.getByLabelText("amount"), { target: { value: "99999999999999999.01" } });
    expect(change).toHaveBeenCalledWith({ amount: "99999999999999999.01" });
    expect(dirty).toHaveBeenLastCalledWith(false);
  });
  it("refuses ambiguous duplicate keys instead of replacing a definition", () => {
    expect(() =>
      updateSource(
        initialPackageSource +
          "\nmetadata: {key: duplicate, name: Duplicate}\n",
        ["metadata", "name"],
        "Changed",
      ),
    ).toThrow();
  });
});
