import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ScheduleFireHistory } from "./schedule-fire-history";
afterEach(() => vi.unstubAllGlobals());
it("distinguishes failed launch receipts from linked successful executions", async () => {
  const common = {
    scheduleId: "s1",
    scheduledAt: "2026-09-08T09:00:00Z",
    updatedAt: "2026-09-08T09:00:00Z",
    engineWorkflowId: "schedule-workflow",
  };
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [
            {
              ...common,
              triggerId: "fire-1",
              engineRunId: "engine-1",
              status: "launch_failed",
              runId: null,
              errorCode: "package_not_found",
            },
            {
              ...common,
              triggerId: "fire-2",
              engineRunId: "engine-2",
              status: "succeeded",
              runId: "run-2",
              errorCode: null,
            },
          ],
        }),
        { headers: { "content-type": "application/json" } },
      ),
    ),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <MemoryRouter>
        <ScheduleFireHistory scheduleId="s1" />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByText("未能启动")).toBeVisible();
  expect(screen.getByText("尚未生成结果")).toBeVisible();
  expect(screen.getByText("package_not_found")).toBeVisible();
  expect(screen.getByRole("link", { name: "查看结果" })).toHaveAttribute(
    "href",
    "/runs/run-2",
  );
  expect(screen.getByText(/execution engine-1/)).toBeInTheDocument();
  expect(screen.getByText(/execution engine-2/)).toBeInTheDocument();
});
