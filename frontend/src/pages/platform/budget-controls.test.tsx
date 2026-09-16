import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { expect, it } from "vitest";
import type { AgentBudget, AgentDefinition, ExecutionOptions, WorkflowDefinition } from "@/lib/types/workflow-platform";
import { BudgetControls, TaskBudgetControls } from "./budget-controls";
import { ModelBudgetSummary } from "./budget-summary";

function pick(label: string, option: string) {
  fireEvent.click(screen.getByRole("combobox", { name: label }));
  fireEvent.click(screen.getByRole("option", { name: option }));
}
it("keeps unlimited, service-controlled and inherited values distinct", () => {
  let latest: AgentBudget = {};
  function Editor() {
    const [value, setValue] = useState<AgentBudget>({ maxTokens: 500, maxOutputTokens: 20 });
    latest = value;
    return <BudgetControls value={value} onChange={setValue} />;
  }
  render(<Editor />);
  pick("累计模型用量方式", "不设限");
  pick("单次输出方式", "由模型服务决定");
  expect(latest).toEqual({ maxTokens: "unlimited", maxOutputTokens: "provider_default" });
  pick("单次输出方式", "指定额度");
  fireEvent.change(screen.getByLabelText("单次输出数值"), { target: { value: "" } });
  expect(latest).toEqual({ maxTokens: "unlimited" });
  pick("累计模型用量方式", "沿用默认");
  expect(latest).toEqual({});
});
it("batch edits preserve other per-agent fields and pending controls are locked", () => {
  const agent: AgentDefinition = { name: "整理助手", inputSchema: {}, outputSchema: {}, strategy: { kind: "model", modelRef: "model", prompt: "read" } };
  const workflow: WorkflowDefinition = { inputSchema: {}, outputSchema: {}, outputMapping: {}, nodes: { one: { uses: "a", inputMapping: {} }, two: { uses: "b", inputMapping: {} } } };
  let latest: ExecutionOptions = {};
  function Editor({ disabled = false }: { disabled?: boolean }) {
    const [value, setValue] = useState<ExecutionOptions>({ agentBudgets: { a: { maxTokens: 50 }, b: { maxTokens: 100 } } });
    latest = value;
    return <TaskBudgetControls agents={{ a: agent, b: { ...agent, name: "检查助手" } }} workflow={workflow} value={value} onChange={setValue} disabled={disabled} />;
  }
  const view = render(<Editor />);
  fireEvent.click(screen.getByText(/用量与时间限制 ·/));
  expect(screen.getByRole("combobox", { name: "累计模型用量方式" })).toHaveTextContent("各助手设置不同");
  pick("单次输出方式", "由模型服务决定");
  expect(latest.agentBudgets).toEqual({ a: { maxTokens: 50, maxOutputTokens: "provider_default" }, b: { maxTokens: 100, maxOutputTokens: "provider_default" } });
  pick("累计模型用量方式", "沿用工作流默认");
  expect(latest.agentBudgets).toEqual({ a: { maxOutputTokens: "provider_default" }, b: { maxOutputTokens: "provider_default" } });
  expect(screen.getByRole("combobox", { name: "累计模型用量方式" })).toHaveTextContent("沿用工作流默认");
  view.rerender(<Editor disabled />);
  expect(screen.getByRole("combobox", { name: "单次输出方式" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "恢复工作流默认设置" })).toBeDisabled();
});
it("renders all budget modes and sources without protocol values or agent identities", () => {
  render(<ModelBudgetSummary settings={{ agents: { privateKey: { name: "研究助手", budget: { maxTokens: "unlimited", maxOutputTokens: "provider_default", deadlineSeconds: 60 }, budgetSources: { maxTokens: "task", maxOutputTokens: "workflow", deadlineSeconds: "platform" } } } }} />);
  const summary = screen.getByRole("region", { name: "模型使用限制" });
  expect(within(summary).getByText(/不设限/)).toBeVisible();
  expect(within(summary).getByText(/由模型服务决定/)).toBeVisible();
  expect(summary).toHaveTextContent("本次设置");
  expect(summary).toHaveTextContent("工作流默认");
  expect(summary).toHaveTextContent("平台默认");
  expect(summary).not.toHaveTextContent(/privateKey|provider_default|unlimited/);
});
