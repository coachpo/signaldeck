import { requestPlatform, toPathSegment } from "@/lib/api-client";
import type { TaskDraft, TaskDraftWrite } from "@/lib/types/task-drafts";
export const taskDraftApi = {
  list: () => requestPlatform<{ items: TaskDraft[] }>("/task-drafts"),
  get: (id: string) => requestPlatform<TaskDraft>(`/task-drafts/${toPathSegment(id)}`),
  save: ({ id, ...body }: TaskDraftWrite & { id: string }) =>
    requestPlatform<TaskDraft>(`/task-drafts/${toPathSegment(id)}`, { method: "PUT", body }),
  delete: ({ id, revision }: { id: string; revision: number }) =>
    requestPlatform<void>(`/task-drafts/${toPathSegment(id)}?revision=${revision}`, { method: "DELETE" }),
};
