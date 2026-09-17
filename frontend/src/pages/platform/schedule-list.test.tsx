import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { stubInsecureContext } from "@/test/insecure-context";
import { SchedulesPage } from "./schedule-list";
import { scheduleTriggerDrafts } from "./schedule-drafts";

afterEach(() => { vi.unstubAllGlobals(); scheduleTriggerDrafts.clear(); });
function stubSchedules(trigger: (body: { triggerId: string }) => Response) {
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
    if (url.endsWith("/trigger")) return trigger(JSON.parse(String(options?.body)));
    throw new Error(`Unexpected ${url}`);
  }));
}
const schedulesPage = () => <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>
  <MemoryRouter><SchedulesPage /></MemoryRouter>
</QueryClientProvider>;
it("retains an uncertain manual execution through leaving and returning", async () => {
  const requests: unknown[] = [];
  stubSchedules((body) => { requests.push(body); throw new TypeError("offline"); });
  const ui = schedulesPage();
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
it("lists schedules over plain HTTP and uses a new request after an accepted execution", async () => {
  stubInsecureContext();
  const identities: string[] = [];
  stubSchedules(({ triggerId }) => {
    identities.push(triggerId);
    return new Response(JSON.stringify({ scheduleId: "s-1", triggerId, status: "accepted" }));
  });
  render(schedulesPage());
  fireEvent.click(await screen.findByRole("button", { name: "立即执行" }));
  expect(await screen.findByText("已请求执行，打开安排可跟进结果。")).toBeVisible();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "立即执行" }));
  await waitFor(() => expect(identities).toHaveLength(2));
  expect(identities[1]).not.toBe(identities[0]);
});
