import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { stubInsecureContext } from "@/test/insecure-context";
import { SchedulePage } from "./schedules";
import { scheduleDrafts, scheduleTriggerDrafts } from "./schedule-drafts";
afterEach(() => { vi.unstubAllGlobals(); scheduleDrafts.clear(); scheduleTriggerDrafts.clear(); });
const packages = {
  items: [
    {
      key: "task-form-fixture",
      name: "Notes",
      definition: {
        agents: { writer: { name: "写作助手", inputSchema: {}, outputSchema: {}, strategy: { kind: "model", modelRef: "model", prompt: "write" } } },
        workflows: {
          capture: {
            name: "Capture",
            nodes: { write: { uses: "writer", inputMapping: {} } },
            inputSchema: {
              type: "object",
              properties: {
                includeRisk: { type: "boolean", "x-signaldeck-schema": "signaldeck.schema/2", default: true },
                title: { type: "string", title: "标题" },
                text: { type: "string", title: "原文" },
              },
              required: ["title", "text"],
            },
          },
        },
      },
    },
  ],
};
it("inherits business input and keeps one creation identity after an uncertain response", async () => {
  const submitted: Record<string, unknown>[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/workflow-packages"))
        return new Response(JSON.stringify(packages));
      if (options?.method === "POST" && url.endsWith("/schedules")) {
        submitted.push(JSON.parse(String(options.body)));
        throw new TypeError("connection lost");
      }
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
  const ui = (
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter
        initialEntries={[
          {
            pathname: "/scheduled-tasks/new",
            state: {
              scheduleInput: {
                packageKey: "task-form-fixture",
                workflowKey: "capture",
                name: "保存会议原文",
                parameters: { title: "会议", text: "原文内容" },
                executionOptions: { agentBudgets: { writer: { maxTokens: "unlimited", maxOutputTokens: "provider_default" } } },
              },
            },
          },
        ]}
      >
        <SchedulePage />
      </MemoryRouter>
    </QueryClientProvider>
  );
  const view = render(ui);
  expect(await screen.findByRole("textbox", { name: "标题" })).toHaveValue(
    "会议",
  );
  expect(screen.getByRole("textbox", { name: "原文" })).toHaveValue("原文内容");
  expect(
    screen.queryByRole("tab", { name: "JSON 输入" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "启用自动执行" }));
  await waitFor(() => expect(submitted).toHaveLength(1));
  await screen.findByText(/尚未确认新安排是否已生效/);
  expect(screen.getByRole("textbox", { name: "原文" })).toBeDisabled();
  view.unmount();
  render(ui);
  expect(await screen.findByRole("textbox", { name: "原文" })).toHaveValue("原文内容");
  expect(screen.getByRole("textbox", { name: "原文" })).toBeDisabled();
  const refresh = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(refresh);
  expect(refresh.defaultPrevented).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "启用自动执行" }));
  await waitFor(() => expect(submitted).toHaveLength(2));
  expect(submitted[1]).toEqual(submitted[0]);
  expect(submitted[0].executionOptions).toEqual({ agentBudgets: { writer: { maxTokens: "unlimited", maxOutputTokens: "provider_default" } } });
  expect(submitted[0].requestId).toEqual(expect.any(String));
  expect(submitted[0].parameters).toEqual({ title: "会议", text: "原文内容" });
});
it("opens a saved schedule over plain HTTP and uses a new request after an accepted execution", async () => {
  stubInsecureContext();
  const identities: string[] = [];
  const schedule = {
    id: "s-1", name: "每天保存会议原文", packageKey: "task-form-fixture", workflowKey: "capture",
    parameters: { title: "会议", text: "原文内容" }, cron: "0 9 * * *", timeZone: "UTC", overlapPolicy: "skip",
    catchupWindowSeconds: 60, paused: false, revision: 1, syncedRevision: 1, syncStatus: "synced", syncErrorCode: null,
  };
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith("/workflow-packages")) return new Response(JSON.stringify(packages));
    if (url.endsWith("/schedules/s-1")) return new Response(JSON.stringify(schedule));
    if (url.endsWith("/fires")) return new Response(JSON.stringify({ items: [] }));
    if (url.endsWith("/preview")) return new Response(JSON.stringify({ scope: "applied", paused: false,
      timeZone: "UTC", times: [], observedAt: "2026-09-12T08:00:00Z", desiredRevision: 1, syncedRevision: 1 }));
    if (url.endsWith("/trigger")) {
      const { triggerId } = JSON.parse(String(options?.body));
      identities.push(triggerId);
      return new Response(JSON.stringify({ scheduleId: "s-1", triggerId, status: "accepted" }));
    }
    throw new Error(`Unexpected request: ${url}`);
  }));
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
      <MemoryRouter initialEntries={["/scheduled-tasks/s-1"]}>
        <Routes><Route path="/scheduled-tasks/:scheduleId" element={<SchedulePage />} /></Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  const trigger = await screen.findByRole("button", { name: "立即执行" });
  await waitFor(() => expect(trigger).toBeEnabled());
  fireEvent.click(trigger);
  expect(await screen.findByText("已接受执行请求")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "立即执行" }));
  await waitFor(() => expect(identities).toHaveLength(2));
  expect(identities[1]).not.toBe(identities[0]);
});
