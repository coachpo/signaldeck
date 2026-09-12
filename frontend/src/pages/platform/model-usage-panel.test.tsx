import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import type { ModelUsage } from "@/lib/types/model-usage";
import { ModelBudgetSummary, ModelUsageDetails, ModelUsagePanel } from "./model-usage-panel";

const state = vi.hoisted(() => ({
  run: {}, day: {},
  selectedDay: { date: "2026-03-29", timezone: "Europe/Helsinki" },
}));
vi.mock("@/hooks/use-model-usage", () => ({ useModelUsage: () => state }));
beforeEach(() => { state.run = {}; state.day = {}; });

const data: ModelUsage = {
  runId: "run-1", runStatus: "failed", date: null, timezone: null,
  windowStart: null, windowEnd: null, asOf: "2026-03-29T01:00:00Z", runDurationMs: 2000,
  summary: {
    modelCalls: 2, confirmedCalls: 1, failedCalls: 1, unconfirmedCalls: 0,
    inputTokens: null, outputTokens: null, durationMs: 1000, usageKnownCalls: 0,
    usageMissingCalls: 2, durationKnownCalls: 2, networkAttempts: 3,
    failedNetworkAttempts: 2, unconfirmedNetworkAttempts: 0, usageCoverage: "none",
  },
  models: [],
};
it("keeps absent provider counters unknown while explaining failed-attempt coverage", () => {
  render(<ModelUsageDetails title="本次模型用量" data={data} />);
  expect(screen.getAllByText("未知")).toHaveLength(2);
  expect(screen.getByText(/2 次缺少完整用量/)).toBeVisible();
  expect(screen.getByText(/失败尝试未报告的消耗不包含在用量中/)).toBeVisible();
  expect(screen.getByText("本次运行耗时：2 秒")).toBeVisible();
});
it("shows an explicitly reported zero and allows the model breakdown to be opened", () => {
  const summary = { ...data.summary, modelCalls: 1, confirmedCalls: 1, failedCalls: 0, inputTokens: 3, outputTokens: 0, usageKnownCalls: 1, usageMissingCalls: 0, usageCoverage: "complete" as const };
  render(<ModelUsageDetails title="用量" data={{ ...data, summary, models: [{ resourceId: "writer", modelId: "model-b", apiStyle: "responses", summary }] }} />);
  expect(screen.getAllByText("0")[0]).toBeVisible();
  expect(screen.queryByText(/缺少完整用量/)).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("按模型查看用量"));
  expect(screen.getByText("模型：model-b")).toBeVisible();
  expect(screen.queryByText(/writer|responses/)).not.toBeInTheDocument();
});
it("offers a read retry after errors and labels today's actual timezone", () => {
  const retry = vi.fn();
  state.day = { isError: true, refetch: retry };
  render(<ModelUsagePanel />);
  expect(screen.getByText(/2026-03-29 · Europe\/Helsinki暂时无法读取/)).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "重新读取用量" }));
  expect(retry).toHaveBeenCalledOnce();
});
it("shows independent effective output limits without changing omitted settings", () => {
  const settings = { agents: {
    writer: { strategy: { kind: "model" }, budget: { maxTokens: 900, maxOutputTokens: 100, maxModelRequests: 3, deadlineSeconds: 60 } },
    reader: { strategy: { kind: "model" }, budget: { maxTokens: 800, maxModelRequests: 2, deadlineSeconds: 30 } },
    save: { strategy: { kind: "deterministic" }, budget: { maxTokens: 500 } },
  } };
  render(<ModelBudgetSummary settings={settings} />);
  expect(screen.getByText(/内容处理 1：总用量额度 900；单次输出 100 计量单位/)).toBeVisible();
  expect(screen.getByText(/内容处理 2：总用量额度 800；单次输出 沿用剩余额度/)).toBeVisible();
  expect(screen.queryByText(/save：/)).not.toBeInTheDocument();
  expect(settings.agents.reader.budget).not.toHaveProperty("maxOutputTokens");
});
