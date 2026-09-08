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
import { queryKeys } from "@/lib/query-keys";
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
  it("edits the same YAML document without erasing nodes, comments or constraints", () => {
    const source = "# operator note\n" + initialPackageSource;
    const onChange = vi.fn();
    render(<PackageStructure source={source} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText("Package name"), {
      target: { value: "Changed" },
    });
    const next = onChange.mock.calls[0][0] as string;
    expect(next).toContain("# operator note");
    expect(parseDefinition(next).metadata.name).toBe("Changed");
    expect(parseDefinition(next).workflows).toEqual(
      parseDefinition(source).workflows,
    );
  });
  it("blocks structure editing for broken YAML and does not silently repair it", () => {
    render(<PackageStructure source="agents: [" onChange={vi.fn()} />);
    expect(screen.getByText("Repair YAML to edit structure")).toBeVisible();
    expect(screen.queryByLabelText("Package name")).not.toBeInTheDocument();
  });
  it("requires explicit application of JSON structural edits and preserves other sections", () => {
    const onChange = vi.fn();
    render(
      <PackageStructure source={initialPackageSource} onChange={onChange} />,
    );
    const agents = {
      ...packageFixture.definition.agents,
      second: packageFixture.definition.agents.assistant,
    };
    fireEvent.change(screen.getByLabelText("Agent definitions"), {
      target: { value: JSON.stringify(agents) },
    });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Apply Agent definitions" }),
    );
    const result = parseDefinition(onChange.mock.calls[0][0]);
    expect(result.agents.second).toBeDefined();
    expect(result.workflows).toEqual(packageFixture.definition.workflows);
  });
  it("blocks save while a structural draft is unapplied and permits explicit discard", async () => {
    renderPage(<PackageEditorPage />);
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Structure" }), {
      button: 0,
    });
    fireEvent.change(screen.getByLabelText("Agent definitions"), {
      target: { value: '{"pending":' },
    });
    expect(screen.getByRole("button", { name: "Save package" })).toBeDisabled();
    expect(screen.getByRole("tab", { name: "YAML" })).toBeDisabled();
    fireEvent.click(
      screen.getByRole("button", { name: "Discard Agent definitions draft" }),
    );
    expect(screen.getByRole("button", { name: "Save package" })).toBeEnabled();
  });
  it("never hydrates the editor from summary metadata", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response({ ...packageFixture, name: "Summary is stale" }),
        ),
    );
    renderPage(<PackageEditorPage />, "/workflow-packages/example");
    expect(await screen.findByLabelText("Workflow Package YAML")).toHaveValue(
      packageFixture.source,
    );
  });
  it("does not allow structural editing when a persisted manifest read fails", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            code: "unavailable",
            message: "Read unavailable",
            details: [],
          }),
          { status: 503, headers: { "content-type": "application/json" } },
        ),
      ),
    );
    renderPage(<PackageEditorPage />, "/workflow-packages/example");
    expect(await screen.findByText("Read unavailable")).toBeVisible();
    expect(
      screen.queryByLabelText("Workflow Package YAML"),
    ).not.toBeInTheDocument();
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
    expect(screen.getByText("first → last")).toBeVisible();
    for (const source of ["control", "input", "condition"])
      expect(screen.getByText(source)).toBeVisible();
    expect(screen.getByText("blocked")).toBeVisible();
    expect(screen.getByText("upstream_failed")).toBeVisible();
  });
  it("renders invocation ownership separately from the dependency graph", () => {
    renderPage(<EvidenceTree evidence={runFixture.evidence} />);
    const tree = screen.getByLabelText("Call ownership tree");
    const node = within(tree)
      .getByRole("link", { name: "node · answer · attempt 1" })
      .closest("li")!;
    expect(
      within(node).getByRole("link", { name: "tool · answer · attempt 1" }),
    ).toHaveAttribute("href", "/?tab=evidence&target=tool-1");
    expect(within(node).getByText("unknown")).toBeVisible();
    expect(within(node).getByText("operation-stable")).toBeVisible();
  });
  it("reports requested cancellation without claiming execution has stopped", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        response({
          ...runFixture,
          cancelRequestedAt: "2026-09-08T00:01:00Z",
        }),
      ),
    );
    renderPage(<RunPage />, "/runs/run-1");
    expect(
      await screen.findByText(
        "Cancellation requested — waiting for execution to stop",
      ),
    ).toBeVisible();
    expect(
      screen.getByRole("button", { name: "Request cancellation" }),
    ).toBeDisabled();
    expect(screen.queryByText("Execution stopped")).not.toBeInTheDocument();
  });
  it("starts a distinct rerun command after navigating to a cached run", async () => {
    const launchIds: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: string, init?: RequestInit) => {
        if (input.endsWith("/rerun")) {
          launchIds.push(JSON.parse(init!.body as string).launchId);
          return response({
            ...runFixture,
            id: launchIds.length === 1 ? "run-b" : "run-c",
          });
        }
        const id = input.split("/").at(-1)!;
        return response({
          ...runFixture,
          id,
          spec: { ...runFixture.spec, runId: id },
        });
      }),
    );
    const { client } = renderPage(<RunPage />, "/runs/run-1");
    await screen.findByRole("button", { name: "Rerun frozen snapshot" });
    client.setQueryData(queryKeys.platform.runs.detail("run-b"), {
      ...runFixture,
      id: "run-b",
      spec: { ...runFixture.spec, runId: "run-b" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Rerun frozen snapshot" }),
    );
    await screen.findByRole("heading", { name: "Run run-b" });
    fireEvent.click(
      screen.getByRole("button", { name: "Rerun frozen snapshot" }),
    );
    await waitFor(() => expect(launchIds).toHaveLength(2));
    expect(launchIds[0]).not.toEqual(launchIds[1]);
  });
  it("validates evidence deep links against the loaded run", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(runFixture)));
    renderPage(<RunPage />, "/runs/run-1?tab=evidence&target=missing");
    expect(
      await screen.findByText("Evidence target does not exist in this run"),
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
    renderPage(<RunPage />, "/runs/run-1");
    fireEvent.click(await screen.findByRole("button", { name: "future" }));
    expect(
      await screen.findByText("Node future: no execution evidence"),
    ).toBeVisible();
    expect(
      screen.queryByText("Evidence target does not exist in this run"),
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
    fireEvent.click(screen.getByRole("button", { name: "Inspect artifact" }));
    expect(await screen.findByLabelText("Artifact content text")).toHaveValue(
      '{"amount":"99999999999999999.01"}',
    );
    rerender(
      <QueryClientProvider client={client}>
        <ArtifactValue label="Output" value={{ other: "value" }} />
      </QueryClientProvider>,
    );
    expect(
      screen.queryByLabelText("Artifact content text"),
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
      config: { name: "Model" },
      hasCredentials: true,
      credentialRevision: "revision-1",
    };
    const fetcher = vi.fn(async (_input: unknown, init?: RequestInit) =>
      response(init?.method === "POST" ? resource : { items: [resource] }),
    );
    vi.stubGlobal("fetch", fetcher);
    renderPage(<ResourcesPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Edit model" }));
    expect(screen.getByLabelText("New credentials JSON")).toHaveValue("");
    fireEvent.change(screen.getByLabelText("New credentials JSON"), {
      target: { value: '{"apiKey":"new-private-value"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save resource" }));
    await waitFor(() =>
      expect(screen.getByLabelText("New credentials JSON")).toHaveValue(""),
    );
    const write = fetcher.mock.calls.find(
      ([, init]) => init?.method === "POST",
    )!;
    expect(JSON.parse(write[1]!.body as string).credentials).toEqual({
      apiKey: "new-private-value",
    });
    expect(document.body.textContent).not.toContain("new-private-value");
  });
  it("does not echo malformed credential drafts into diagnostics", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ items: [] })));
    renderPage(<ResourcesPage />);
    fireEvent.change(screen.getByLabelText("Resource ID"), {
      target: { value: "model" },
    });
    fireEvent.change(screen.getByLabelText("New credentials JSON"), {
      target: { value: '{"apiKey":"private-secret' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save resource" }));
    expect(
      await screen.findByText(
        "New credentials must be a JSON object with string values.",
      ),
    ).toBeVisible();
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
      await screen.findByRole("link", { name: "Open external/weather" }),
    ).toHaveAttribute("href", "https://weather.example/workspace");
    expect(safePluginPageUrl("javascript:alert(1)")).toBeNull();
    expect(safePluginPageUrl("data:text/html,x")).toBeNull();
  });
  it("applies advanced parameters through the same codec without losing optional omission", () => {
    const change = vi.fn(),
      dirty = vi.fn();
    render(
      <LaunchInputs
        schema={{
          type: "object",
          properties: {
            amount: { type: "string" },
            optional: { type: "string" },
          },
          required: ["amount"],
        }}
        value={{ amount: "1.00" }}
        onChange={change}
        onDirtyChange={dirty}
      />,
    );
    fireEvent.mouseDown(screen.getByRole("tab", { name: "Advanced JSON" }), {
      button: 0,
    });
    fireEvent.change(screen.getByLabelText("Parameters JSON"), {
      target: { value: '{"amount":"99999999999999999.01"}' },
    });
    expect(dirty).toHaveBeenLastCalledWith(true);
    expect(change).not.toHaveBeenCalled();
    fireEvent.click(
      screen.getByRole("button", { name: "Apply parameters JSON" }),
    );
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
