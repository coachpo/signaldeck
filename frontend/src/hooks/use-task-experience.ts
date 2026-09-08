import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { taskExperienceApi as api } from "@/lib/api/task-experience";
import { queryKeys } from "@/lib/query-keys";
import type { PrepareInput } from "@/lib/types/task-experience";
export function useTaskPreparation(input: PrepareInput, enabled: boolean) {
  return useQuery({
    queryKey: queryKeys.platform.workflowPackages.preparation(input),
    queryFn: () => api.prepare(input),
    enabled,
    retry: false,
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
  });
}
export function useTaskPresets() {
  return useQuery({
    queryKey: queryKeys.platform.taskPresets.all,
    queryFn: api.presets,
  });
}
export function useTaskReuse(id?: string) {
  return useQuery({
    queryKey: queryKeys.platform.runs.reuse(id ?? ""),
    queryFn: () => api.reuse(id!),
    enabled: !!id,
  });
}
export function useTaskMutations() {
  const client = useQueryClient();
  return {
    prepare: useMutation({ mutationFn: api.prepare }),
    launch: useMutation({
      mutationFn: api.launch,
      onSuccess: () =>
        client.invalidateQueries({ queryKey: queryKeys.platform.runs.all }),
    }),
    savePreset: useMutation({
      mutationFn: api.savePreset,
      onSuccess: () =>
        client.invalidateQueries({
          queryKey: queryKeys.platform.taskPresets.all,
        }),
    }),
    deletePreset: useMutation({
      mutationFn: api.deletePreset,
      onSuccess: () =>
        client.invalidateQueries({
          queryKey: queryKeys.platform.taskPresets.all,
        }),
    }),
  };
}

export function useConnectionPresets() {
  return useQuery({
    queryKey: queryKeys.platform.resources.connectionPresets(),
    queryFn: api.connectionPresets,
  });
}
