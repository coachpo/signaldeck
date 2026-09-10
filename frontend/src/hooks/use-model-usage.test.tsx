import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { expect, it, vi } from "vitest";
import { modelUsageApi } from "@/lib/api/model-usage";
import { currentUsageDay, useModelUsage } from "./use-model-usage";

it("uses the selected IANA local date on each side of midnight and DST", () => {
  expect(currentUsageDay(new Date("2026-03-28T21:59:59Z"), "Europe/Helsinki").date).toBe("2026-03-28");
  expect(currentUsageDay(new Date("2026-03-28T22:00:00Z"), "Europe/Helsinki").date).toBe("2026-03-29");
  expect(currentUsageDay(new Date("2026-03-29T21:00:00Z"), "Europe/Helsinki").date).toBe("2026-03-30");
});
it("requests only the day summary when no run is selected", async () => {
  const run = vi.spyOn(modelUsageApi, "run").mockRejectedValue(new Error("not requested"));
  const day = vi.spyOn(modelUsageApi, "day").mockRejectedValue(new Error("offline"));
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const view = renderHook(() => useModelUsage(), { wrapper: ({ children }: { children: ReactNode }) => <QueryClientProvider client={client}>{children}</QueryClientProvider> });
  await waitFor(() => expect(view.result.current.day.isError).toBe(true));
  expect(day).toHaveBeenCalledWith(view.result.current.selectedDay.date, view.result.current.selectedDay.timezone);
  expect(run).not.toHaveBeenCalled();
  view.unmount();
  client.clear();
});
