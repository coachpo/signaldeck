import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { MemoryRouter } from "react-router";
import { TaskPreparation, SafeSettings } from "./task-preparation";
import { connectionName } from "./task-labels";

it("keeps arbitrary scope keys and values literal, even when named like former business aliases", () => {
  render(<SafeSettings value={{ collection: "model", accountId: "name", scope: { includeRisk: false, reportId: "resources" } }} />);
  for (const text of ["collection", "model", "accountId", "name", "scope", "includeRisk", "reportId", "resources"]) expect(screen.getByText(text)).toBeVisible();
  expect(connectionName("", "example/notes")).toBe("example/notes");
  expect(connectionName("Operator name", "example/notes")).toBe("Operator name");
});

it("shows current model observation without changing configuration readiness", () => {
  render(<MemoryRouter><TaskPreparation preparation={{
    packageKey: "p", workflowKey: "w", packageHash: "h", ready: true, bindingToken: "b",
    issues: [], changedBindings: [], previousBindings: {}, effectiveSettings: {},
    requirements: [{ id: "m", kind: "model", name: "我的模型", configured: true,
      hasCredentials: true, config: {}, observation: "failed", modelObservation: {
        status: "failed", observedAt: "2026-09-10T09:00:00Z", errorCode: "model_http_error",
        errorCategory: "quota", runId: "run-1", evidenceId: "model-1",
      } }],
  }} /></MemoryRouter>);
  expect(screen.getByText(/配置已就绪/)).toBeVisible();
  expect(screen.getByText(/模型服务额度不足/)).toBeVisible();
  expect(screen.getByRole("link", { name: "查看最近调用证据" })).toHaveAttribute("href", "/runs/run-1?tab=evidence&target=model-1");
});

it("shows arbitrary business scope and changed bindings before technical disclosure", () => {
  render(<MemoryRouter><TaskPreparation preparation={{
    packageKey: "p", workflowKey: "w", packageHash: "h", ready: true, bindingToken: "b",
    issues: [], changedBindings: ["tool-x"], previousBindings: {}, effectiveSettings: {},
    requirements: [{ id: "tool-x", kind: "tool", name: "配置名称", configured: true, hasCredentials: false,
      config: { pluginId: "remote/tool", scope: { arbitraryZone: "place-x", reportId: "literal-id" }, maxConcurrentCalls: 4 }, observation: "not_observed" }],
  }} /></MemoryRouter>);
  expect(screen.getByText(/与上次相比/)).toBeVisible();
  expect(screen.getAllByText("arbitraryZone").filter((node) => !node.closest("details"))[0]).toBeVisible();
  expect(screen.getAllByText("literal-id").filter((node) => !node.closest("details"))[0]).toBeVisible();
  const technical = screen.getByText("连接技术配置（完整原值）").closest("details");
  expect(technical).not.toHaveAttribute("open");
  fireEvent.click(screen.getByText("连接技术配置（完整原值）"));
  expect(screen.getByText("remote/tool")).toBeVisible();
});
