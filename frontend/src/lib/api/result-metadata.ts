import { requestPlatform } from "@/lib/api-client";
import type { ResultMetadata, ResultMetadataPatch, AttentionList, AttentionItem } from "@/lib/types/result-metadata";

export const resultMetadataApi = {
  get: (id: string) => requestPlatform<ResultMetadata>(`/runs/${encodeURIComponent(id)}/metadata`),
  patch: (id: string, body: ResultMetadataPatch) => requestPlatform<ResultMetadata>(`/runs/${encodeURIComponent(id)}/metadata`, { method: "PATCH", body }),
};
export const attentionApi = {
  list: (query: string) => requestPlatform<AttentionList>(`/attention?${query}`),
  mark: (id: string, expectedRevision: number, isRead: boolean) => requestPlatform<AttentionItem>(`/attention/${encodeURIComponent(id)}`, { method: "PATCH", body: { expectedRevision, isRead } }),
};
