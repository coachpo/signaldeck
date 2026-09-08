import { useState } from "react";
import { useQuery, useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import type { Preparation } from "@/lib/types/task-experience";
import { queryKeys } from "@/lib/query-keys";
import { resultsApi, rerunResult } from "@/lib/api/results";
import { isRunActive } from "./use-workflow-platform";
type PendingRerun = { launchId: string; preparation: Preparation };
const pendingReruns = new WeakMap<QueryClient, Map<string, PendingRerun>>();

/** Keep uncertain commands through evidence navigation without persisting business data. */
export function usePendingResultRerun(runId: string) {
  const client = useQueryClient();
  const [pending, setPending] = useState(() => pendingReruns.get(client)?.get(runId));
  return {
    pending,
    retain(command: PendingRerun) {
      let commands = pendingReruns.get(client);
      if (!commands) {
        commands = new Map();
        pendingReruns.set(client, commands);
      }
      commands.set(runId, command);
      setPending(command);
    },
    clear() {
      pendingReruns.get(client)?.delete(runId);
      setPending(undefined);
    },
  };
}
export function useResultHistory(query: string) {
  return useQuery({
    queryKey: queryKeys.platform.runs.history(
      Object.fromEntries(new URLSearchParams(query)),
    ),
    queryFn: () => resultsApi.history(query),
    refetchInterval: (q) =>
      q.state.data?.items.some(isRunActive) ? 1000 : false,
  });
}
export function useRunResult(id?: string) {
  return useQuery({
    queryKey: queryKeys.platform.runs.result(id ?? ""),
    queryFn: () => resultsApi.result(id!),
    enabled: !!id,
    refetchInterval: (q) =>
      q.state.data?.status === "queued" || q.state.data?.status === "running"
        ? 1000
        : false,
  });
}

export function useResultRerun() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      launchId,
      bindingToken,
    }: {
      id: string;
      launchId: string;
      bindingToken: string;
    }) => rerunResult(id, launchId, bindingToken),
    onSuccess: () =>
      client.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
  });
}

export function useInvalidateResultHistory() {
  const client = useQueryClient();
  return (query: string) =>
    client.invalidateQueries({
      queryKey: queryKeys.platform.runs.history(
        Object.fromEntries(new URLSearchParams(query)),
      ),
      exact: true,
      refetchType: "none",
    });
}
