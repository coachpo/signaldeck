import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";
import { queryKeys } from "@/lib/query-keys";
import { RunPage } from "./runs";
import { ResultHistoryPage } from "./result-history";
import { runFixture } from "./fixtures";
import type { RunResult } from "@/lib/types/result";
vi.mock("@/hooks/use-model-usage", () => ({
  useModelUsage: () => ({ run: {}, day: {}, selectedDay: { date: "2026-09-10", timezone: "UTC" } }),
}));
const result: RunResult = {
  runId: "run-1",
  title: "我的研究",
  status: "running",
  contentStatus: "available",
  body: "# 研究正文\n本次结论",
  receipt: null,
  dataTime: "2026-09-08",
  createdAt: "2026-09-08T01:00:00Z",
  finishedAt: null,
  cancelRequestedAt: null,
  origin: { kind: "manual" },
  sources: ["公开资料"],
  missing: ["未取得最新价格"],
  attachments: [],
  unknownEvidenceIds: [],
  freshness: [],
  errorCode: null,
};
const reuse = {
  sourceRunId: "run-1",
  packageKey: "research_notes",
  workflowKey: "capture",
  packageHash: "hash",
  parameters: { title: "原文标题", text: "原始内容" },
  inputSchema: { type: "object" },
};
const preparation = {
  ready: true,
  bindingToken: "binding-1",
  changedBindings: ["notes"],
  previousBindings: { notes: { location: "旧位置" } },
  effectiveSettings: { location: "新位置" },
  requirements: [],
  issues: [],
};
function response(data: unknown, status = 200) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "content-type": "application/json" },
  });
}
function mount(path = "/runs/run-1", cachedHistory?: unknown) {
  const client = new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 15_000 },
      mutations: { retry: false },
    },
  });
  if (cachedHistory)
    client.setQueryData(
      queryKeys.platform.runs.history({ q: "旧", limit: "25" }),
      cachedHistory,
    );
  const router = createMemoryRouter(
    [
      { path: "/runs/:runId", element: <RunPage /> },
      { path: "/runs", element: <ResultHistoryPage /> },
    ],
    { initialEntries: [path] },
  );
  render(
    <QueryClientProvider client={client}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}
function fetcher(overrides: Partial<RunResult> = {}) {
  return vi.fn(async (url: string) =>
    url.endsWith("/metadata")
      ? response({ runId: "run-1", isFavorite: false, isRead: false, note: "", revision: 0 })
      : url.endsWith("/result")
      ? response({ ...result, ...overrides })
      : url.endsWith("/reuse")
        ? response(reuse)
        : url.endsWith("/prepare")
          ? response(preparation)
          : response(runFixture),
  );
}
afterEach(() => vi.unstubAllGlobals());
describe("ordinary results", () => {
  it("keeps declared receipt and complete input available behind disclosure", async () => {
    vi.stubGlobal("fetch", fetcher({ sections: [
      { kind: "markdown", label: "声明正文", value: "# 唯一正文" },
      { kind: "receipt", label: "保存信息", value: { arbitrary: "receipt-only" } },
    ] }));
    mount();
    expect(await screen.findByRole("heading", { name: "唯一正文" })).toBeVisible();
    expect(screen.getByText("保存信息（完整原值）").closest("details")).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("保存信息（完整原值）"));
    expect(screen.getByText("receipt-only")).toBeVisible();
    expect(screen.getByText("本次输入（完整原值）").closest("details")).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("本次输入（完整原值）"));
    expect(await screen.findByText("原始内容")).toBeVisible();
  });

  it("explains a model failure while retaining the input-reuse and evidence destinations", async () => {
    vi.stubGlobal("fetch", fetcher({ status: "failed", errorCode: "model_http_error", errorCategory: "quota", missing: [] }));
    mount();
    expect(await screen.findByText(/模型服务额度不足/)).toBeVisible();
    expect(screen.getByRole("link", { name: "保留输入并检查连接" })).toHaveAttribute("href", "/tasks/new?fromRun=run-1");
    expect(screen.getByRole("link", { name: "技术详情与调用证据" })).toHaveAttribute("href", "/runs/run-1?tab=evidence");
  });
  it("shows body, missing information and provenance before technical evidence", async () => {
    vi.stubGlobal("fetch", fetcher());
    mount();
    expect(
      await screen.findByRole("heading", { name: "研究正文" }),
    ).toBeVisible();
    expect(screen.getByText("未取得最新价格")).toBeVisible();
    expect(screen.getByText("公开资料")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "技术详情与调用证据" }),
    ).toHaveAttribute("href", "/runs/run-1?tab=evidence");
    expect(
      screen.queryByRole("tab", { name: "Run graph" }),
    ).not.toBeInTheDocument();
  });
  it("preserves history filters through evidence selection, technical tabs and return", async () => {
    vi.stubGlobal("fetch", fetcher());
    const history = "q=archive&status=succeeded&offset=25";
    const router = mount(`/runs/run-1?history=${encodeURIComponent(history)}`);
    fireEvent.click(
      await screen.findByRole("link", { name: "技术详情与调用证据" }),
    );
    const evidenceLink = await screen.findByRole("link", {
      name: "node · answer · attempt 1",
    });
    fireEvent.click(evidenceLink);
    expect(
      new URLSearchParams(router.state.location.search).get("history"),
    ).toBe(history);
    fireEvent.mouseDown(
      screen.getByRole("tab", { name: "Immutable snapshot" }),
      { button: 0, ctrlKey: false },
    );
    await waitFor(() =>
      expect(new URLSearchParams(router.state.location.search).get("tab")).toBe(
        "snapshot",
      ),
    );
    fireEvent.click(screen.getByRole("link", { name: "返回结果" }));
    const back = await screen.findByRole("link", { name: "全部结果" });
    expect(back).toHaveAttribute("href", `/runs?${history}`);
  });
  it("does not claim cancellation has stopped execution or unknown writes succeeded", async () => {
    vi.stubGlobal(
      "fetch",
      fetcher({
        cancelRequestedAt: "2026-09-08T01:01:00Z",
        contentStatus: "unknown",
        body: null,
      }),
    );
    mount();
    expect(
      await screen.findByText("已请求取消，正在等待执行停止"),
    ).toBeVisible();
    expect(screen.getByRole("button", { name: "取消本次运行" })).toBeDisabled();
    expect(screen.getByText("保存状态待核实")).toBeVisible();
    expect(screen.queryByText("本次运行已取消")).not.toBeInTheDocument();
  });
  it("reviews changed bindings before rerun and retains identity after an uncertain response", async () => {
    const requests: { launchId: string; bindingToken: string }[] = [];
    const fallback = fetcher();
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith("/rerun")) {
          requests.push(JSON.parse(init!.body as string));
          return response(
            { code: "unavailable", message: "响应未知", details: [] },
            503,
          );
        }
        return fallback(url);
      }),
    );
    mount();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "再运行一次" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "再运行一次" }));
    expect(
      await screen.findByText(
        "与上次相比，连接或业务范围已变化，请核对后确认开始。",
      ),
    ).toBeVisible();
    expect(requests).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { name: "确认并开始新运行" }));
    await screen.findByText("响应未知");
    fireEvent.click(screen.getByRole("button", { name: "确认并开始新运行" }));
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[0]).toEqual(requests[1]);
    expect(requests[0].bindingToken).toBe("binding-1");
  });
  it("creates a fresh rerun command after moving to another result", async () => {
    const identities: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url.endsWith("/rerun")) {
          identities.push(JSON.parse(init!.body as string).launchId);
          return response({
            ...runFixture,
            id: identities.length === 1 ? "run-b" : "run-c",
          });
        }
        if (url.endsWith("/result"))
          return response({
            ...result,
            runId: url.includes("run-b") ? "run-b" : "run-1",
          });
        if (url.endsWith("/reuse")) return response(reuse);
        if (url.endsWith("/prepare")) return response(preparation);
        return response(runFixture);
      }),
    );
    const router = mount();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "再运行一次" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "再运行一次" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "确认并开始新运行" }),
    );
    await waitFor(() =>
      expect(router.state.location.pathname).toBe("/runs/run-b"),
    );
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "确认并开始新运行" }),
      ).not.toBeInTheDocument(),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "再运行一次" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "再运行一次" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "确认并开始新运行" }),
    );
    await waitFor(() => expect(identities).toHaveLength(2));
    expect(identities[0]).not.toBe(identities[1]);
  });
  it("keeps an uncertain rerun identity and binding while visiting its technical evidence", async () => {
    const requests: { launchId: string; bindingToken: string }[] = [];
    const fallback = fetcher({ runId: "rerun-navigation" });
    vi.stubGlobal("fetch", vi.fn(async (url: string, init?: RequestInit) => {
      if (url.endsWith("/rerun")) {
        requests.push(JSON.parse(init!.body as string));
        if (requests.length === 1)
          return response({ code: "unavailable", message: "响应未知", details: [] }, 503);
        return response({ ...runFixture, id: "accepted-rerun" });
      }
      return fallback(url);
    }));
    const router = mount("/runs/rerun-navigation");
    await waitFor(() => expect(screen.getByRole("button", { name: "再运行一次" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "再运行一次" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认并开始新运行" }));
    await screen.findByText("响应未知");
    fireEvent.click(screen.getByRole("link", { name: "技术详情与调用证据" }));
    fireEvent.click(await screen.findByRole("link", { name: "返回结果" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "再运行一次" })).toBeEnabled());
    fireEvent.click(screen.getByRole("button", { name: "再运行一次" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认并开始新运行" }));
    await waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[1]).toEqual(requests[0]);
    await waitFor(() => expect(router.state.location.pathname).toBe("/runs/accepted-rerun"));
  });
  it("requires explicit verification before repeating an unknown write", async () => {
    vi.stubGlobal("fetch", fetcher({ contentStatus: "unknown", body: null }));
    mount();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "再运行一次" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "再运行一次" }));
    const start = await screen.findByRole("button", {
      name: "确认并开始新运行",
    });
    expect(start).toBeDisabled();
    fireEvent.click(
      screen.getByRole("checkbox", {
        name: "我已核实目标位置与执行证据，确认需要再次执行",
      }),
    );
    expect(start).toBeEnabled();
  });
  it("opens only the explicitly projected frozen plugin link", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.endsWith("/result")
          ? response({
              ...result,
              sections: [
                {
                  kind: "link",
                  label: "打开报告",
                  value: { reportId: 7, slug: "report-seven" },
                  href: "https://finance.example/reports?report=report-seven",
                  pluginId: "finance",
                },
              ],
            })
          : url.endsWith("/reuse")
            ? response(reuse)
            : response({
                ...runFixture,
                spec: {
                  ...runFixture.spec,
                  pluginReleases: [
                    {
                      pluginId: "finance",
                      pageUrl: "https://finance.example/reports",
                    },
                  ],
                },
              }),
      ),
    );
    mount();
    expect(
      await screen.findByRole("link", { name: "打开报告" }),
    ).toHaveAttribute(
      "href",
      "https://finance.example/reports?report=report-seven",
    );
  });
  it("recognizes the projected artifact reference and offers a download", async () => {
    vi.stubGlobal(
      "fetch",
      fetcher({
        attachments: [
          {
            kind: "artifact",
            label: "正文附件",
            reference: {
              digest: `sha256:${"a".repeat(64)}`,
              sizeBytes: 24,
              mediaType: "text/plain",
            },
          },
        ],
      }),
    );
    mount();
    expect(
      await screen.findByRole("button", { name: "下载附件（text/plain）" }),
    ).toBeVisible();
  });
  it("reads a large JSON artifact without requiring technical evidence", async () => {
    const fallback = fetcher({
      body: null,
      attachments: [
        {
          kind: "artifact",
          label: "正文附件",
          reference: {
            digest: `sha256:${"a".repeat(64)}`,
            sizeBytes: 100000,
            mediaType: "application/json",
          },
        },
      ],
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) =>
        url.includes("/artifacts/")
          ? new Response(JSON.stringify({ text: "# 完整正文\n附件中的原文" }))
          : fallback(url),
      ),
    );
    mount();
    expect(
      screen.queryByText("尚无可阅读的正文或保存回执"),
    ).not.toBeInTheDocument();
    const read = await screen.findByRole("button", { name: "阅读附件正文" });
    expect(screen.queryByText("# 完整正文 附件中的原文")).not.toBeInTheDocument();
    fireEvent.click(read);
    expect(await screen.findByText("# 完整正文 附件中的原文")).toBeVisible();
  });
  it("refreshes from the first page with a new snapshot while retaining filters", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/workflow-packages")) return response([]);
        urls.push(url);
        return response({
          items: [{ ...runFixture, title: "旧结果", hasUnknownEffects: true }],
          total: 60,
          limit: 25,
          offset: 25,
          snapshotAt: "2026-09-08T01:00:00Z",
        });
      }),
    );
    mount("/runs?q=旧&offset=25&snapshotAt=2026-09-08T01%3A00%3A00Z", {
      items: [{ ...runFixture, title: "缓存首屏" }],
      total: 59,
      offset: 0,
      limit: 25,
      snapshotAt: "2026-09-08T00:00:00Z",
    });
    expect(await screen.findByText("保存状态待核实")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "刷新" }));
    await waitFor(() => expect(urls).toHaveLength(2));
    const query = new URL(urls[1], "http://localhost").searchParams;
    expect(query.get("q")).toBe("旧");
    expect(query.has("offset")).toBe(false);
    expect(query.has("snapshotAt")).toBe(false);
  });
  it("keeps server filters and snapshot watermark when paging", async () => {
    const urls: string[] = [];
    vi.stubGlobal(
      "fetch",
      vi.fn(async (url: string) => {
        if (url.endsWith("/workflow-packages")) return response([]);
        urls.push(url);
        return response({
          items: [{ ...runFixture, title: "旧结果" }],
          total: 60,
          limit: 25,
          offset: 0,
          snapshotAt: "2026-09-08T01:00:00Z",
        });
      }),
    );
    mount("/runs?q=旧&status=succeeded");
    expect(await screen.findByText("旧结果")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "下一页" }));
    await waitFor(() => expect(urls.length).toBe(2));
    const query = new URL(urls[1], "http://localhost").searchParams;
    expect(query.get("q")).toBe("旧");
    expect(query.get("status")).toBe("succeeded");
    expect(query.get("offset")).toBe("25");
    expect(query.get("snapshotAt")).toBe("2026-09-08T01:00:00Z");
  });
});
