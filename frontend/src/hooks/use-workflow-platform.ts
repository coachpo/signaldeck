import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { workflowPlatformApi as api } from "@/lib/api/workflow-platform";
import { queryKeys } from "@/lib/query-keys";
import type {
  Json,
  PluginRelease,
  RunSummary,
} from "@/lib/types/workflow-platform";
const keys = queryKeys.platform;
export function isRunActive(run?: RunSummary) {
  return run?.status === "queued" || run?.status === "running";
}
export function usePackages() {
  return useQuery({
    queryKey: keys.workflowPackages.list(),
    queryFn: api.packages,
  });
}
export function usePackage(key?: string) {
  return useQuery({
    queryKey: keys.workflowPackages.detail(key ?? ""),
    queryFn: () => api.package(key!),
    enabled: !!key,
  });
}
export function usePlatformRuns() {
  return useQuery({
    queryKey: keys.runs.list(),
    queryFn: api.runs,
    refetchInterval: (q) =>
      q.state.data?.items.some(isRunActive) ? 1000 : false,
  });
}
export function usePlatformRun(id?: string) {
  return useQuery({
    queryKey: keys.runs.detail(id ?? ""),
    queryFn: () => api.run(id!),
    enabled: !!id,
    refetchInterval: (q) => (isRunActive(q.state.data) ? 1000 : false),
  });
}
export function useResources() {
  return useQuery({ queryKey: keys.resources.all, queryFn: api.resources });
}
export function usePlugins() {
  return useQuery({ queryKey: keys.plugins.all, queryFn: api.plugins });
}
export function usePlatformSchedules() {
  return useQuery({
    queryKey: keys.schedules.list(),
    queryFn: api.schedules,
    refetchInterval: (q) =>
      q.state.data?.items.some((s) => s.syncStatus === "pending")
        ? 1000
        : false,
  });
}
export function usePlatformSchedule(id?: string) {
  return useQuery({
    queryKey: keys.schedules.detail(id ?? ""),
    queryFn: () => api.schedule(id!),
    enabled: !!id,
    refetchInterval: (q) =>
      q.state.data?.syncStatus === "pending" ? 1000 : false,
  });
}
export function useScheduleFires(id: string) {
  return useQuery({
    queryKey: keys.schedules.fires(id),
    queryFn: () => api.scheduleFires(id),
    refetchInterval: (q) =>
      q.state.data?.items.some(
        (fire) => fire.status === "pending" || fire.status === "launched",
      )
        ? 1000
        : false,
  });
}
export function useArtifact(digest?: string) {
  return useQuery({
    queryKey: keys.artifacts.detail(digest ?? ""),
    queryFn: () => api.artifact(digest!),
    enabled: !!digest,
    staleTime: Infinity,
  });
}
export function usePlatformMutations() {
  const client = useQueryClient();
  const invalidate = (...scopes: readonly (readonly unknown[])[]) =>
    Promise.all(
      scopes.map((queryKey) => client.invalidateQueries({ queryKey })),
    );
  return {
    validate: useMutation({ mutationFn: api.validate }),
    savePackage: useMutation({
      mutationFn: ({ source, key }: { source: string; key?: string }) =>
        api.savePackage(source, key),
      onSuccess: () => invalidate(keys.workflowPackages.all),
    }),
    launch: useMutation({
      mutationFn: ({
        key,
        workflowKey,
        parameters,
        launchId,
      }: {
        key: string;
        workflowKey: string;
        parameters: Json;
        launchId: string;
      }) => api.launch(key, workflowKey, parameters, launchId),
      onSuccess: () => invalidate(keys.runs.all),
    }),
    cancel: useMutation({
      mutationFn: api.cancel,
      onSuccess: () => invalidate(keys.runs.all, keys.schedules.all),
    }),
    rerun: useMutation({
      mutationFn: ({ id, launchId }: { id: string; launchId: string }) =>
        api.rerun(id, launchId),
      onSuccess: () => invalidate(keys.runs.all),
    }),
    saveResource: useMutation({
      mutationFn: api.saveResource,
      onSuccess: () => invalidate(keys.resources.all),
    }),
    savePlugin: useMutation({
      mutationFn: ({
        release,
        enabled,
      }: {
        release: PluginRelease;
        enabled: boolean;
      }) => api.savePlugin(release, enabled),
      onSuccess: () => invalidate(keys.plugins.all, keys.resources.all),
    }),
    enablePlugin: useMutation({
      mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
        api.enablePlugin(id, enabled),
      onSuccess: () => invalidate(keys.plugins.all, keys.resources.all),
    }),
    saveSchedule: useMutation({
      mutationFn: api.saveSchedule,
      onSuccess: () => invalidate(keys.schedules.all),
    }),
    deleteSchedule: useMutation({
      mutationFn: api.deleteSchedule,
      onSuccess: () => invalidate(keys.schedules.all, keys.runs.all),
    }),
    triggerSchedule: useMutation({
      mutationFn: ({ id, triggerId }: { id: string; triggerId: string }) =>
        api.triggerSchedule(id, triggerId),
      onSuccess: () => invalidate(keys.schedules.all, keys.runs.all),
    }),
  };
}
