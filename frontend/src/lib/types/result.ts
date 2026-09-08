import type { Json, RunSummary, LaunchOrigin } from "./workflow-platform";
export interface ResultAttachment {
  kind: "artifact" | "report" | "note";
  label: string;
  reference: Json;
  evidenceId?: string | null;
  pluginId?: string | null;
}
export interface RunResult {
  runId: string;
  title: string;
  status: RunSummary["status"];
  contentStatus: "not_available" | "available" | "partial" | "unknown";
  body: string | null;
  receipt: Json;
  dataTime: string | null;
  createdAt: string;
  finishedAt: string | null;
  cancelRequestedAt: string | null;
  origin: LaunchOrigin;
  sources: Json[];
  missing: string[];
  attachments: ResultAttachment[];
  unknownEvidenceIds: string[];
  freshness: Json[];
  errorCode: string | null;
}
export interface RunHistory {
  snapshotAt: string;
  items: (RunSummary & { title: string; hasUnknownEffects?: boolean })[];
  total: number;
  offset: number;
  limit: number;
}
