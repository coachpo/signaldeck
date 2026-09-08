import { afterEach, describe, expect, it, vi } from "vitest";
import { workflowPlatformApi as api } from "./workflow-platform";
import type { Json, Schedule } from "@/lib/types/workflow-platform";
afterEach(() => vi.unstubAllGlobals());
function mock() {
  const fetcher = vi
    .fn()
    .mockResolvedValue(
      new Response("{}", { headers: { "content-type": "application/json" } }),
    );
  vi.stubGlobal("fetch", fetcher);
  return fetcher;
}
describe("workflow platform transport", () => {
  it("submits canonical camelCase launch identity without changing parameter values", async () => {
    const fetcher = mock();
    await api.launch(
      "space/key",
      "main",
      { amount: "123456789123456789.01" },
      "stable-launch",
    );
    expect(fetcher.mock.calls[0][0]).toMatch(
      /\/api\/workflow-packages\/space%2Fkey\/launches$/,
    );
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      workflowKey: "main",
      parameters: { amount: "123456789123456789.01" },
      launchId: "stable-launch",
    });
  });
  it.each([0, false, null, [], "", ["first", "second"]] as Json[])(
    "preserves a non-object parameter value in manual and scheduled writes: %j",
    async (parameters) => {
      const fetcher = mock();
      await api.launch("package", "main", parameters, "launch-value");
      expect(JSON.parse(fetcher.mock.calls[0][1].body).parameters).toEqual(
        parameters,
      );
      fetcher.mockResolvedValueOnce(
        new Response("{}", { headers: { "content-type": "application/json" } }),
      );
      await api.saveSchedule({
        name: "Values",
        packageKey: "package",
        workflowKey: "main",
        parameters,
        cron: "0 9 * * *",
        timeZone: "UTC",
        overlapPolicy: "skip",
        catchupWindowSeconds: 60,
        paused: true,
      });
      expect(JSON.parse(fetcher.mock.calls[1][1].body).parameters).toEqual(
        parameters,
      );
    },
  );
  it("keeps read-only synchronization projections out of closed schedule writes", async () => {
    const fetcher = mock();
    const schedule: Schedule = {
      id: "s1",
      name: "Daily",
      packageKey: "p",
      workflowKey: "main",
      parameters: {},
      cron: "0 9 * * *",
      timeZone: "Europe/Helsinki",
      overlapPolicy: "buffer_one",
      catchupWindowSeconds: 3600,
      paused: false,
      revision: 4,
      syncedRevision: 3,
      syncStatus: "failed",
      syncErrorCode: "engine_unavailable",
    };
    await api.saveSchedule(schedule);
    const payload = JSON.parse(fetcher.mock.calls[0][1].body);
    expect(payload).toEqual({
      name: "Daily",
      packageKey: "p",
      workflowKey: "main",
      parameters: {},
      cron: "0 9 * * *",
      timeZone: "Europe/Helsinki",
      overlapPolicy: "buffer_one",
      catchupWindowSeconds: 3600,
      paused: false,
    });
  });
  it("does not turn read-only credential revisions into resource writes", async () => {
    const fetcher = mock();
    const read = {
      resourceId: "model",
      kind: "model" as const,
      config: { name: "Model" },
      hasCredentials: true,
      credentialRevision: "read-only-revision",
    };
    await api.saveResource(read);
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      resourceId: "model",
      kind: "model",
      config: { name: "Model" },
    });
  });
  it("encodes both parts of the qualified plugin identity", async () => {
    const fetcher = mock();
    await api.enablePlugin("publisher/plugin", true);
    expect(fetcher.mock.calls[0][0]).toMatch(
      /\/api\/plugins\/publisher\/plugin$/,
    );
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      enabled: true,
    });
  });
  it("passes a stable schedule trigger identity without inventing a run", async () => {
    const fetcher = mock();
    await api.triggerSchedule("s1", "trigger-1");
    expect(JSON.parse(fetcher.mock.calls[0][1].body)).toEqual({
      triggerId: "trigger-1",
    });
  });
});
