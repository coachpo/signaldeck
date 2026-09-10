import { requestPlatform } from "@/lib/api-client";
import type { ModelUsage } from "@/lib/types/model-usage";

export const modelUsageApi = {
  run: (runId: string) =>
    requestPlatform<ModelUsage>(`/runs/${encodeURIComponent(runId)}/usage`),
  day: (date: string, timezone: string) =>
    requestPlatform<ModelUsage>(`/model-usage?${new URLSearchParams({ date, timezone })}`),
};
