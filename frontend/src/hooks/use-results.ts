import { useState } from "react";
import { useQuery, useMutation, useQueryClient, type QueryClient } from "@tanstack/react-query";
import type { Preparation } from "@/lib/types/task-experience";
import { queryKeys } from "@/lib/query-keys";
import { resultsApi, rerunResult } from "@/lib/api/results";
import { isRunActive } from "./use-workflow-platform";
type PendingRerun = { launchId: string; preparation: Preparation };
const pendingReruns = new WeakMap<QueryClient, Map<string, PendingRerun>>();
function readPendingRerun(runId: string): PendingRerun | undefined {
  try {
    const value = JSON.parse(sessionStorage.getItem(`signaldeck:pending-rerun:${runId}`) ?? "null");
    if (!value || typeof value.launchId !== "string" || typeof value.bindingToken !== "string") return undefined;
    return { launchId: value.launchId, preparation: {
      packageKey: typeof value.packageKey === "string" ? value.packageKey : "",
      workflowKey: typeof value.workflowKey === "string" ? value.workflowKey : "",
      packageHash: typeof value.packageHash === "string" ? value.packageHash : "",
      bindingToken: value.bindingToken, ready: true, requirements: [], issues: [], changedBindings: [], previousBindings: {}, effectiveSettings: {},
    } };
  } catch { return undefined; }
}

/** Preserve the same uncertain command across navigation and refresh in this tab. */
export function usePendingResultRerun(runId: string) {
  const client = useQueryClient();
  const [pending, setPending] = useState(() => pendingReruns.get(client)?.get(runId) ?? readPendingRerun(runId));
  return {
    pending,
    retain(command: PendingRerun) {
      let commands = pendingReruns.get(client);
      if (!commands) {
        commands = new Map();
        pendingReruns.set(client, commands);
      }
      commands.set(runId, command);
      try { sessionStorage.setItem(`signaldeck:pending-rerun:${runId}`, JSON.stringify({
        launchId: command.launchId, bindingToken: command.preparation.bindingToken,
        packageKey: command.preparation.packageKey, workflowKey: command.preparation.workflowKey, packageHash: command.preparation.packageHash,
      })); } catch { /* In-memory recovery remains available when browser storage is disabled. */ }
      setPending(command);
    },
    clear() {
      pendingReruns.get(client)?.delete(runId);
      try { sessionStorage.removeItem(`signaldeck:pending-rerun:${runId}`); } catch { /* Browser storage may be unavailable. */ }
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
