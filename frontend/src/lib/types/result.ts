import type { ResultMetadata } from "./result-metadata";
import type { Json, RunSummary, LaunchOrigin, ModelErrorCategory } from "./workflow-platform";
export interface ResultAttachment {
  kind: "artifact";
  label: string;
  reference: Json;
  nodeId?: string | null;
  operationId?: string | null;
  toolEvidenceId?: string | null;
  evidenceId?: string | null;
  pluginId?: string | null;
}
export interface ResultSection {
  kind: "markdown" | "value" | "receipt" | "sources" | "dataTime" | "notice" | "link";
  label: string;
  value: Json;
  evidenceId?: string | null;
  nodeId?: string | null;
  operationId?: string | null;
  toolEvidenceId?: string | null;
  pluginId?: string | null;
  href?: string | null;
  severity?: "info" | "warning" | "missing" | null;
}
export interface RunResult {
  errorCategory?: ModelErrorCategory | null;
  sections?: ResultSection[];
  skipped?: string[];
  deferredSections?: string[];
  executionIssues?: string[];
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
  readUnknownEvidenceIds?: string[];
  freshness: Json[];
  errorCode: string | null;
}
export interface RunHistory {
  snapshotAt: string;
  items: (RunSummary & { title: string; hasUnknownEffects?: boolean; metadata?: ResultMetadata })[];
  total: number;
  offset: number;
  limit: number;
}
