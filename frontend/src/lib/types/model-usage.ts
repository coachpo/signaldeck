export type ModelUsageSummary = {
  modelCalls: number;
  confirmedCalls: number;
  failedCalls: number;
  unconfirmedCalls: number;
  inputTokens: number | null;
  outputTokens: number | null;
  durationMs: number | null;
  usageKnownCalls: number;
  usageMissingCalls: number;
  durationKnownCalls: number;
  networkAttempts: number;
  failedNetworkAttempts: number;
  unconfirmedNetworkAttempts: number;
  usageCoverage: "complete" | "partial" | "none";
};
export type ModelUsage = {
  runId: string | null;
  runStatus: string | null;
  date: string | null;
  timezone: string | null;
  windowStart: string | null;
  windowEnd: string | null;
  asOf: string;
  runDurationMs: number | null;
  summary: ModelUsageSummary;
  models: {
    resourceId: string;
    modelId: string;
    apiStyle: string;
    summary: ModelUsageSummary;
  }[];
};
