import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { AttentionPage } from "./attention";
function response(value: unknown) { return new Response(JSON.stringify(value), { headers: { "content-type": "application/json" } }); }
afterEach(() => vi.unstubAllGlobals());
it("keeps viewed unknown operations actionable and provides no-Run fire navigation", async () => {
  let read = false;
  const patches: object[] = [];
  const base = { occurredAt: "2026-09-10T09:00:00Z", errorCode: null, errorCategory: null, scheduleId: null, triggerId: null, revision: 0 };
  vi.stubGlobal("fetch", vi.fn(async (_url: string, options?: RequestInit) => {
    const unknown = { ...base, id: "u1", kind: "run", title: "待核实", status: "failed", runId: "r1", hasUnknownEffects: true, isRead: read };
    if (options?.method === "PATCH") { patches.push(JSON.parse(options.body as string)); read = true; return response({ ...unknown, isRead: true, revision: 1 }); }
    return response({ items: [unknown, { ...base, id: "f1", kind: "fire", title: "安排未能启动", status: "launch_failed", runId: null, scheduleId: "s1", triggerId: "fire-1", hasUnknownEffects: false, isRead: false, errorCode: "package_not_found" }], total: 2, limit: 25, offset: 0, snapshotAt: "2026-09-10T10:00:00Z", historyScope: "all_current_records" });
  }));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}><MemoryRouter><AttentionPage /></MemoryRouter></QueryClientProvider>);
  expect(await screen.findByRole("link", { name: "核实执行证据" })).toHaveAttribute("href", "/runs/r1?tab=evidence");
  expect(screen.getByRole("link", { name: "查看安排与失败原因" })).toHaveAttribute("href", "/scheduled-tasks/s1");
  expect(screen.getByText(/找不到任务定义/)).toBeVisible();
  expect(patches).toEqual([]);
  fireEvent.click(screen.getAllByRole("button", { name: "已查看本次更新" })[0]);
  await waitFor(() => expect(screen.getByText("更新已查看")).toBeVisible());
  expect(screen.getByRole("link", { name: "核实执行证据" })).toBeVisible();
  expect(patches).toEqual([{ expectedRevision: 0, isRead: true }]);
});
