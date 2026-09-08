import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import { workflowPlatformApi as api } from "@/lib/api/workflow-platform";
import { queryKeys } from "@/lib/query-keys";
import { isRunActive, usePlatformMutations } from "./use-workflow-platform";
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
