import { afterEach, expect, it, vi } from "vitest";
import { taskExperienceApi as api } from "./task-experience";
import { taskDraftApi } from "./task-drafts";
import { workflowPlatformApi } from "./workflow-platform";
import { queryKeys } from "@/lib/query-keys";
import { scheduleConfigKey } from "@/pages/platform/schedule-drafts";
import type { ExecutionOptions, ScheduleConfig } from "@/lib/types/workflow-platform";

afterEach(() => vi.unstubAllGlobals());
const executionOptions: ExecutionOptions = { agentBudgets: { writer: { maxTokens: "unlimited", maxOutputTokens: "provider_default", deadlineSeconds: 90 } } };
it("preserves budget selections through preparation, historical reuse, presets, drafts and schedules", async () => {
  const fetcher = vi.fn().mockImplementation(async () => new Response("{}", { headers: { "content-type": "application/json" } }));
  vi.stubGlobal("fetch", fetcher);
  const input = { packageKey: "p", workflowKey: "main", parameters: false, executionOptions };
  await api.prepare(input);
  await api.launch({ ...input, sourceRunId: "old", launchId: "stable", bindingToken: "bound" });
  await api.savePreset({ ...input, id: "preset", name: "Saved", packageHash: "hash", hasParameters: true, isFavorite: false, isPinned: false });
  await taskDraftApi.save({ ...input, id: "draft", revision: 0, name: "Draft", packageHash: "hash", sourceRunId: "old", hasParameters: true, jsonText: null, launchId: "stable", pending: true, bindingToken: "bound" });
  await workflowPlatformApi.saveSchedule({ ...input, id: "schedule", name: "Repeat", cron: "0 9 * * *", timeZone: "UTC", overlapPolicy: "skip", catchupWindowSeconds: 60, paused: false });
  for (const [, init] of fetcher.mock.calls) {
    const body = JSON.parse(init.body);
    expect(body.executionOptions).toEqual(executionOptions);
    expect(body.parameters).toBe(false);
  }
  expect(JSON.parse(fetcher.mock.calls[1][1].body)).toEqual({ parameters: false, executionOptions, launchId: "stable", bindingToken: "bound" });
});
it("invalidates preparation identity and schedule dirty state when only budgets change", () => {
  const original = { packageKey: "p", workflowKey: "main", parameters: {} };
  expect(queryKeys.platform.workflowPackages.preparation(original)).not.toEqual(queryKeys.platform.workflowPackages.preparation({ ...original, executionOptions }));
  const schedule: ScheduleConfig = { ...original, name: "Repeat", cron: "0 9 * * *", timeZone: "UTC", overlapPolicy: "skip", catchupWindowSeconds: 60, paused: false };
  expect(scheduleConfigKey(schedule)).not.toBe(scheduleConfigKey({ ...schedule, executionOptions }));
});
