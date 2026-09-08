import { useMutation, useQuery } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { requestPlatform, toPathSegment } from "@/lib/api-client";
export interface SchedulePreview {
  timeZone: string;
  times: string[];
  observedAt: string;
  scope: "draft" | "applied";
  desiredRevision: number | null;
  syncedRevision: number | null;
  appliedNote: string | null;
  paused: boolean;
}
export function useSchedulePreview() {
  return useMutation({
    mutationFn: (calendar: { cron: string; timeZone: string }) =>
      requestPlatform<SchedulePreview>("/schedules/preview", {
        method: "POST",
        body: calendar,
      }),
  });
}
export function useAppliedSchedulePreview(
  id: string | undefined,
  revision?: number,
) {
  return useQuery({
    queryKey: queryKeys.platform.schedules.preview(id ?? "", revision),
    queryFn: () =>
      requestPlatform<SchedulePreview>(
        `/schedules/${toPathSegment(id!)}/preview`,
      ),
    enabled: !!id,
    retry: false,
    staleTime: 60_000,
  });
}
