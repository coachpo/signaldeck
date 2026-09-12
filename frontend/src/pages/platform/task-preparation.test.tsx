import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { TaskPreparation, SafeSettings } from "./task-preparation";
import { connectionName } from "./task-labels";
vi.mock("@/hooks/use-workflow-platform", () => ({ usePlugins: () => ({ data: { items: [] } }) }));
it("preserves arbitrary business values and avoids falling back to internal connection identifiers", () => {
  render(<SafeSettings value={{ collection: "model", accountId: "name", scope: { includeRisk: false, reportId: "resources" } }} />);
  for (const text of ["collection", "model", "accountId", "name", "scope", "includeRisk", "reportId", "resources"]) expect(screen.getByText(text)).toBeVisible();
  expect(connectionName("", "example/notes")).toBe("服务连接");
  expect(connectionName("example/notes", "example/notes")).toBe("服务连接");
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
});
it("shows business scope and previous settings without exposing platform bindings or issues", () => {
  render(<MemoryRouter><TaskPreparation preparation={{
    packageKey: "p", workflowKey: "w", packageHash: "h", ready: true, bindingToken: "b",
    issues: ["binding_invalid"], changedBindings: ["resources"],
    previousBindings: { resources: { "internal-resource": { name: "先前连接", pluginId: "private/plugin", credentialRevision: "hidden-revision", scope: { region: "previous-place" } } } },
    effectiveSettings: { deadlineSeconds: 120, maxParallelNodes: 2, failurePolicy: "continue_independent" },
    requirements: [{ id: "tool-x", kind: "tool", name: "配置名称", configured: true, hasCredentials: false,
      config: { pluginId: "remote/tool", scope: { arbitraryZone: "place-x", reportId: "literal-id" }, maxConcurrentCalls: 4 }, observation: "not_observed" }],
  }} /></MemoryRouter>);
  expect(screen.getByText(/与上次相比/)).toBeVisible();
  expect(screen.getByText("literal-id")).toBeVisible();
  expect(screen.getByText(/最多同时处理 4 项/)).toBeVisible();
  expect(screen.getByText(/先前连接/)).toBeInTheDocument();
  expect(document.body.textContent).not.toMatch(/tool-x|remote\/tool|private\/plugin|hidden-revision|binding_invalid|credentialRevision|技术详情|完整原值/);
});
