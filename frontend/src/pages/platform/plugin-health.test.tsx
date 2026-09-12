import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
import { PluginHealth } from "./plugin-health";
it("reports recorded failure and recovery without exposing identifiers or raw error codes", () => {
  render(<MemoryRouter><PluginHealth health={{ status: "failed", observedAt: "2026-09-08T10:00:00Z", errorCode: "plugin_unavailable", runId: "run-1", operationId: "operation-1", evidenceId: "network-1" }} /></MemoryRouter>);
  expect(screen.getByText("最近使用情况")).toBeVisible();
  expect(screen.getByText("最近使用失败")).toBeVisible();
  expect(screen.getByRole("link", { name: "查看最近任务记录" })).toHaveAttribute("href", "/runs/run-1?tab=evidence&target=network-1");
  expect(document.body.textContent).not.toMatch(/plugin_unavailable|operation-1|run-1|network-1/);
});
it("does not equate a lack of observations with availability", () => {
  render(<MemoryRouter><PluginHealth health={{ status: "not_observed", observedAt: null, errorCode: null, runId: null, operationId: null, evidenceId: null }} /></MemoryRouter>);
  expect(screen.getByText(/尚无使用记录，是否可用需要通过任务执行确认/)).toBeVisible();
});
it("preserves uncertainty and tells the user to check effects before repeating", () => {
  render(<MemoryRouter><PluginHealth health={{ status: "unknown", observedAt: "2026-09-08T10:00:00Z", errorCode: null, runId: "a", operationId: "b", evidenceId: null }} /></MemoryRouter>);
  expect(screen.getByText(/尚不能确认服务是否完成了操作/)).toBeVisible();
});
