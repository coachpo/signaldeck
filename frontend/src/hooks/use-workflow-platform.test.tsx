import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { workflowPlatformApi as api } from "@/lib/api/workflow-platform";
import { queryKeys } from "@/lib/query-keys";
import { isRunActive, usePlatformMutations, usePlatformSchedule, usePlatformSchedules } from "./use-workflow-platform";
import { runFixture } from "@/pages/platform/fixtures";
describe("platform query mutations", () => {
  it("invalidates run and schedule scopes after cancellation", async () => {
    vi.spyOn(api, "cancel").mockResolvedValue({
      ...runFixture,
      cancelRequestedAt: "2026-09-08T00:00:01Z",
    });
    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(usePlatformMutations, {
      wrapper: ({ children }: { children: ReactNode }) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      ),
    });
    await act(() => result.current.cancel.mutateAsync("run-1"));
    await waitFor(() =>
      expect(invalidate).toHaveBeenCalledWith({
        queryKey: queryKeys.platform.runs.all,
      }),
    );
    expect(invalidate).toHaveBeenCalledWith({
      queryKey: queryKeys.platform.schedules.all,
    });
  });
  it("polls only known active states, including a cancellation that is still running", () => {
    expect(isRunActive(undefined)).toBe(false);
    expect(isRunActive(runFixture)).toBe(true);
    expect(isRunActive({ ...runFixture, cancelRequestedAt: "now" })).toBe(true);
    for (const status of ["succeeded", "failed", "cancelled"] as const)
      expect(isRunActive({ ...runFixture, status })).toBe(false);
  });
});

it("updates failed schedule synchronization automatically after recovery and stops polling", async () => {
  vi.useFakeTimers();
  const failed = {
    id: "recovering", name: "Daily", packageKey: "package", workflowKey: "main", parameters: {},
    cron: "0 9 * * *", timeZone: "UTC", overlapPolicy: "skip" as const, catchupWindowSeconds: 60,
    paused: false, revision: 2, syncedRevision: 1, syncStatus: "failed" as const, syncErrorCode: "unavailable",
  };
  const recovered = { ...failed, syncStatus: "synced" as const, syncedRevision: 2, syncErrorCode: null };
  const detail = vi.spyOn(api, "schedule").mockResolvedValueOnce(failed).mockResolvedValue(recovered);
  const list = vi.spyOn(api, "schedules").mockResolvedValueOnce({ items: [failed] }).mockResolvedValue({ items: [recovered] });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = renderHook(() => ({ detail: usePlatformSchedule("recovering"), list: usePlatformSchedules() }), {
    wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  });
  try {
    await act(async () => { await vi.advanceTimersByTimeAsync(1); });
    expect(view.result.current.detail.data?.syncStatus).toBe("failed");
    expect(view.result.current.list.data?.items[0].syncStatus).toBe("failed");
    await act(async () => { await vi.advanceTimersByTimeAsync(5001); });
    expect(view.result.current.detail.data?.syncStatus).toBe("synced");
    expect(view.result.current.list.data?.items[0].syncStatus).toBe("synced");
    await act(async () => { await vi.advanceTimersByTimeAsync(10000); });
    expect(detail).toHaveBeenCalledTimes(2);
    expect(list).toHaveBeenCalledTimes(2);
  } finally {
    view.unmount(); client.clear(); vi.useRealTimers(); vi.restoreAllMocks();
  }
});
