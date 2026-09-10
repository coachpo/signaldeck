import { ApiRequestError } from "@/lib/api-client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { resultMetadataApi, attentionApi } from "@/lib/api/result-metadata";
import type { ResultMetadataPatch } from "@/lib/types/result-metadata";

export function useResultMetadata(runId: string) {
  return useQuery({ queryKey: queryKeys.platform.runs.metadata(runId), queryFn: () => resultMetadataApi.get(runId) });
}
export function usePatchResultMetadata(runId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (patch: ResultMetadataPatch) => resultMetadataApi.patch(runId, patch),
    onError: (error) => {
      if (error instanceof ApiRequestError && error.status === 409)
        void client.invalidateQueries({ queryKey: queryKeys.platform.runs.all });
    },
    onSuccess: async (data) => {
      client.setQueryData(queryKeys.platform.runs.metadata(runId), data);
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
        client.invalidateQueries({ queryKey: queryKeys.platform.attention.all }),
      ]);
    },
  });
}
export function useAttention(query: string) {
  return useQuery({
    queryKey: queryKeys.platform.attention.list(Object.fromEntries(new URLSearchParams(query))),
    queryFn: () => attentionApi.list(query),
    refetchInterval: 15_000,
  });
}
export function useMarkAttention() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ id, revision, isRead }: { id: string; revision: number; isRead: boolean }) => attentionApi.mark(id, revision, isRead),
    onSuccess: () => client.invalidateQueries({ queryKey: queryKeys.platform.attention.all }),
  });
}
