import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";
import { PluginHealth } from "./plugin-health";
it("reports an observation timestamp and links the recorded evidence without claiming live health", () => {
  render(
    <MemoryRouter>
      <PluginHealth
        health={{
          status: "failed",
          observedAt: "2026-09-08T10:00:00Z",
          errorCode: "plugin_unavailable",
          runId: "run-1",
          operationId: "operation-1",
          evidenceId: "network-1",
        }}
      />
    </MemoryRouter>,
  );
  expect(screen.getByText("Last observed call")).toBeVisible();
  expect(screen.getByText("2026-09-08T10:00:00Z")).toBeVisible();
  expect(screen.getByText("plugin_unavailable")).toBeVisible();
  expect(screen.getByRole("link")).toHaveAttribute(
    "href",
    "/runs/run-1?tab=evidence&target=network-1",
  );
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});
it("does not equate a lack of observations with availability", () => {
  render(
    <MemoryRouter>
      <PluginHealth
        health={{
          status: "not_observed",
          observedAt: null,
          errorCode: null,
          runId: null,
          operationId: null,
          evidenceId: null,
        }}
      />
    </MemoryRouter>,
  );
  expect(screen.getByText("No observations")).toBeVisible();
  expect(screen.queryByText("healthy")).not.toBeInTheDocument();
});
