import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { SchedulesPage } from "./schedule-list";
import { scheduleTriggerDrafts } from "./schedule-drafts";

afterEach(() => { vi.unstubAllGlobals(); scheduleTriggerDrafts.clear(); });
it("retains an uncertain manual execution through leaving and returning", async () => {
  const requests: unknown[] = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith("/workflow-packages")) return new Response(JSON.stringify({ items: [] }));
    if (url.endsWith("/schedules")) return new Response(JSON.stringify({ items: [{
      id: "s-1", name: "每天整理", packageKey: "p-1", workflowKey: "w-1", parameters: {},
      cron: "0 9 * * *", timeZone: "UTC", overlapPolicy: "skip", catchupWindowSeconds: 60,
      paused: true, revision: 1, syncedRevision: 1, syncStatus: "synced", syncErrorCode: null,
    }] }));
    if (url.endsWith("/fires")) return new Response(JSON.stringify({ items: [] }));
    if (url.endsWith("/preview")) return new Response(JSON.stringify({ scope: "applied", paused: true,
      timeZone: "UTC", times: [], observedAt: "2026-09-12T08:00:00Z", desiredRevision: 1, syncedRevision: 1 }));
    if (url.endsWith("/trigger")) { requests.push(JSON.parse(String(options?.body))); throw new TypeError("offline"); }
    throw new Error(`Unexpected ${url}`);
  }));
  const ui = <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
    <MemoryRouter><SchedulesPage /></MemoryRouter>
  </QueryClientProvider>;
  const view = render(ui);
  fireEvent.click(await screen.findByRole("button", { name: "立即执行" }));
  await waitFor(() => expect(requests).toHaveLength(1));
  await screen.findByText(/执行请求尚未确认/);
  expect(screen.getByRole("button", { name: "恢复" })).toBeDisabled();
  view.unmount();
  render(ui);
  fireEvent.click(await screen.findByRole("button", { name: "确认执行请求" }));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests[1]).toEqual(requests[0]);
});
