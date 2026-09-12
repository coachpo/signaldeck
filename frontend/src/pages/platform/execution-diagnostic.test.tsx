import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
import { ExecutionDiagnostic, ModelObservationDetails } from "./execution-diagnostic";

it("explains known quota errors without exposing implementation codes", () => {
  render(<ExecutionDiagnostic code="model_http_error" category="quota" />);
  expect(screen.getByText(/模型服务额度不足/)).toBeVisible();
  expect(screen.queryByText("model_http_error")).not.toBeInTheDocument();
  expect(screen.queryByText("原始错误码")).not.toBeInTheDocument();
});
it("does not reinterpret historical HTTP errors as quota or input errors", () => {
  render(<ExecutionDiagnostic code="model_http_error" />);
  expect(screen.getByText(/具体原因未知/)).toBeVisible();
  expect(screen.queryByText(/额度不足/)).not.toBeInTheDocument();
});
it("explains a reported output limit violation even with unknown model category", () => {
  render(<ExecutionDiagnostic code="model_output_limit_exceeded" category="unknown" />);
  expect(screen.getByText(/输出超过本次上限/)).toBeVisible();
  expect(screen.getByText(/已发生的用量仍保留/)).toBeVisible();
  expect(screen.queryByText(/具体原因未知/)).not.toBeInTheDocument();
});
it("preserves an output limit diagnosis through an aggregate workflow failure", () => {
  render(<ExecutionDiagnostic code="workflow_nodes_failed" category="output_limit" />);
  expect(screen.getByText(/输出超过本次上限/)).toBeVisible();
  expect(screen.queryByText(/不接受本次输入/)).not.toBeInTheDocument();
});
it("explains an unusable reply without implying that contacting the model failed", () => {
  render(<ExecutionDiagnostic code="agent_output_invalid" />);
  expect(screen.getByText("模型没有按任务要求提供可用结果。可以重试，或检查助手的结果要求。")).toBeVisible();
  expect(screen.queryByText(/具体原因未知|额度不足|认证失败|agent_output_invalid|JSON|schema|原响应/)).not.toBeInTheDocument();
});
it("shows authentication handling and an exact recent evidence link", () => {
  render(<MemoryRouter><ModelObservationDetails observation={{
    status: "failed", observedAt: "2026-09-10T09:00:00Z", errorCode: "model_http_error",
    errorCategory: "authentication", runId: "run/one", evidenceId: "model:1",
  }} /></MemoryRouter>);
  expect(screen.getByText(/模型服务认证失败/)).toBeVisible();
  expect(screen.getByRole("link", { name: "查看最近执行过程" })).toHaveAttribute("href", "/runs/run%2Fone?tab=evidence&target=model%3A1");
});
it("does not turn absent current-version observations into an online claim", () => {
  render(<ModelObservationDetails />);
  expect(screen.getByText("当前连接还没有使用记录")).toBeVisible();
  expect(screen.getByText(/不代表此刻一定可用/)).toBeVisible();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
