import { requestPlatform, toPathSegment as segment } from "@/lib/api-client";
import type { RunSummary } from "@/lib/types/workflow-platform";
import type {
  ConnectionPreset,
  Preparation,
  PrepareInput,
  PresetWrite,
  ReuseInput,
  TaskPreset,
} from "@/lib/types/task-experience";
export const taskExperienceApi = {
  connectionPresets: () =>
    requestPlatform<{ items: ConnectionPreset[] }>("/connection-presets"),
  prepare: ({ packageKey, ...body }: PrepareInput) =>
    requestPlatform<Preparation>(
      `/workflow-packages/${segment(packageKey)}/prepare`,
      { method: "POST", body },
    ),
  reuse: (id: string) =>
    requestPlatform<ReuseInput>(`/runs/${segment(id)}/reuse`),
  launch: ({
    packageKey,
    sourceRunId,
    ...body
  }: PrepareInput & { launchId: string; bindingToken: string }) =>
    sourceRunId
      ? requestPlatform<RunSummary>(`/runs/${segment(sourceRunId)}/reuse`, {
          method: "POST",
          body: {
            parameters: body.parameters,
            launchId: body.launchId,
            bindingToken: body.bindingToken,
          },
        })
      : requestPlatform<RunSummary>(
          `/workflow-packages/${segment(packageKey)}/launches`,
          { method: "POST", body },
        ),
  presets: () => requestPlatform<{ items: TaskPreset[] }>("/task-presets"),
  savePreset: (body: PresetWrite & { id?: string }) => {
    const { id, ...fields } = body;
    return requestPlatform<TaskPreset>(
      id ? `/task-presets/${segment(id)}` : "/task-presets",
      {
        method: id ? "PUT" : "POST",
        body: id
          ? {
              name: fields.name,
              packageHash: fields.packageHash,
              parameters: fields.parameters,
              hasParameters: fields.hasParameters,
              isFavorite: fields.isFavorite,
              isPinned: fields.isPinned,
            }
          : fields,
      },
    );
  },
  deletePreset: (id: string) =>
    requestPlatform<void>(`/task-presets/${segment(id)}`, { method: "DELETE" }),
};
