import type { ScheduleConfig } from "@/lib/types/workflow-platform";

export type ScheduleDraft = {
  value: ScheduleConfig;
  savedValue: string;
  creationUncertain: boolean;
  triggerId: string;
  triggerUncertain: boolean;
};
// Business inputs stay in the current application session, never browser storage.
export const scheduleDrafts = new Map<string, ScheduleDraft>();
export function scheduleConfigKey(value: ScheduleConfig) {
  return JSON.stringify({ name: value.name, packageKey: value.packageKey, workflowKey: value.workflowKey,
    parameters: value.parameters, cron: value.cron, timeZone: value.timeZone,
    overlapPolicy: value.overlapPolicy, catchupWindowSeconds: value.catchupWindowSeconds, paused: value.paused });
}
export const scheduleTriggerDrafts = new Map<string, string>();
