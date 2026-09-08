import {
  requestPlatform,
  requestPlatformText,
  downloadPlatformFile,
  toPathSegment as segment,
} from "@/lib/api-client";
import type {
  Json,
  Plugin,
  PluginRelease,
  Resource,
  ResourceWrite,
  RunDetail,
  RunSummary,
  Schedule,
  ScheduleConfig,
  ScheduleFire,
  ValidationResult,
  WorkflowPackage,
} from "@/lib/types/workflow-platform";
export const workflowPlatformApi = {
  packages: () =>
    requestPlatform<{ items: WorkflowPackage[] }>("/workflow-packages"),
  package: (key: string) =>
    requestPlatform<WorkflowPackage>(`/workflow-packages/${segment(key)}`),
  savePackage: (source: string, key?: string) =>
    requestPlatform<WorkflowPackage>(
      key ? `/workflow-packages/${segment(key)}` : "/workflow-packages",
      { method: key ? "PATCH" : "POST", body: { manifestSource: source } },
    ),
  validate: (source: string) =>
    requestPlatform<ValidationResult>("/workflow-packages/validate-manifest", {
      method: "POST",
      body: { manifestSource: source },
    }),
  launch: (
    key: string,
    workflowKey: string,
    parameters: Json,
    launchId: string,
  ) =>
    requestPlatform<RunSummary>(`/workflow-packages/${segment(key)}/launches`, {
      method: "POST",
      body: { workflowKey, parameters, launchId },
    }),
  runs: () => requestPlatform<{ items: RunSummary[] }>("/runs"),
  run: (id: string) => requestPlatform<RunDetail>(`/runs/${segment(id)}`),
  cancel: (id: string) =>
    requestPlatform<RunSummary>(`/runs/${segment(id)}/cancel`, {
      method: "POST",
    }),
  rerun: (id: string, launchId: string) =>
    requestPlatform<RunSummary>(`/runs/${segment(id)}/rerun`, {
      method: "POST",
      body: { launchId },
    }),
  resources: () => requestPlatform<{ items: Resource[] }>("/resources"),
  saveResource: (body: ResourceWrite) =>
    requestPlatform<Resource>("/resources", {
      method: "POST",
      body: {
        resourceId: body.resourceId,
        kind: body.kind,
        config: body.config,
        ...(body.credentials !== undefined
          ? { credentials: body.credentials }
          : {}),
      },
    }),
  plugins: () => requestPlatform<{ items: Plugin[] }>("/plugins"),
  savePlugin: (release: PluginRelease, enabled: boolean) =>
    requestPlatform<Plugin>("/plugins", {
      method: "POST",
      body: { release, enabled },
    }),
  enablePlugin: (id: string, enabled: boolean) =>
    requestPlatform<Plugin>(
      `/plugins/${id.split("/").map(segment).join("/")}`,
      { method: "PATCH", body: { enabled } },
    ),
  schedules: () => requestPlatform<{ items: Schedule[] }>("/schedules"),
  schedule: (id: string) =>
    requestPlatform<Schedule>(`/schedules/${segment(id)}`),
  scheduleFires: (id: string) =>
    requestPlatform<{ items: ScheduleFire[] }>(
      `/schedules/${segment(id)}/fires`,
    ),
  saveSchedule: (body: ScheduleConfig) =>
    requestPlatform<Schedule>(
      body.id ? `/schedules/${segment(body.id)}` : "/schedules",
      {
        method: body.id ? "PATCH" : "POST",
        body: {
          name: body.name,
          packageKey: body.packageKey,
          workflowKey: body.workflowKey,
          parameters: body.parameters,
          cron: body.cron,
          timeZone: body.timeZone,
          overlapPolicy: body.overlapPolicy,
          catchupWindowSeconds: body.catchupWindowSeconds,
          paused: body.paused,
        },
      },
    ),
  deleteSchedule: (id: string) =>
    requestPlatform<void>(`/schedules/${segment(id)}`, { method: "DELETE" }),
  triggerSchedule: (id: string, triggerId: string) =>
    requestPlatform<{ triggerId: string; status: "accepted" }>(
      `/schedules/${segment(id)}/trigger`,
      { method: "POST", body: { triggerId } },
    ),
  artifact: (digest: string) =>
    requestPlatformText(`/artifacts/${segment(digest)}`),
  downloadArtifact: (digest: string) =>
    downloadPlatformFile(`/artifacts/${segment(digest)}`, { filename: digest }),
};
