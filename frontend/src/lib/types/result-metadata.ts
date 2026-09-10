import type { ModelErrorCategory } from "./workflow-platform";

export interface ResultMetadata {
  runId: string;
  revision: number;
  isFavorite: boolean;
  isRead: boolean;
  note: string;
  updatedAt: string | null;
}
export type ResultMetadataPatch = { expectedRevision: number } & Partial<Pick<ResultMetadata, "isFavorite" | "isRead" | "note">>;
export interface AttentionItem {
  id: string;
  kind: "run" | "fire";
  title: string;
  status: string;
  runId: string | null;
  scheduleId: string | null;
  triggerId: string | null;
  occurredAt: string;
  hasUnknownEffects: boolean;
  hasUnknownResults?: boolean;
  errorCode: string | null;
  errorCategory: ModelErrorCategory | null;
  isRead: boolean;
  revision: number;
}
export interface AttentionList {
  items: AttentionItem[];
  total: number;
  limit: number;
  offset: number;
  snapshotAt: string;
  historyScope: "all_current_records";
}
