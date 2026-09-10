import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { taskDraftApi } from "@/lib/api/task-drafts";
import { queryKeys } from "@/lib/query-keys";
export function useTaskDrafts() {
  return useQuery({ queryKey: queryKeys.platform.taskDrafts.all, queryFn: taskDraftApi.list });
}
export function useTaskDraft(id?: string) {
  return useQuery({ queryKey: queryKeys.platform.taskDrafts.detail(id ?? ""), queryFn: () => taskDraftApi.get(id!), enabled: !!id });
}
export function useTaskDraftMutations() {
  const client = useQueryClient();
  const invalidate = () => client.invalidateQueries({ queryKey: queryKeys.platform.taskDrafts.all });
  return {
    save: useMutation({ mutationFn: taskDraftApi.save, onSuccess: (draft) => { client.setQueryData(queryKeys.platform.taskDrafts.detail(draft.id), draft); return invalidate(); } }),
    remove: useMutation({ mutationFn: taskDraftApi.delete, onSuccess: invalidate }),
  };
}
