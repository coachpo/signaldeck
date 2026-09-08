import { requestPlatform } from "@/lib/api-client";
import type { RunHistory, RunResult } from "@/lib/types/result";
export const resultsApi = {
  history: (query: string) => requestPlatform<RunHistory>(`/runs?${query}`),
  result: (id: string) =>
    requestPlatform<RunResult>(`/runs/${encodeURIComponent(id)}/result`),
};
export const rerunResult = (
  id: string,
  launchId: string,
  bindingToken: string,
) =>
  requestPlatform<import("@/lib/types/workflow-platform").RunSummary>(
    `/runs/${encodeURIComponent(id)}/rerun`,
    { method: "POST", body: { launchId, bindingToken } },
  );
