import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { SchedulePage } from "./schedules";
afterEach(() => vi.unstubAllGlobals());
it("inherits business input and keeps one creation identity after an uncertain response", async () => {
  const submitted: Record<string, unknown>[] = [];
  const packages = {
    items: [
      {
        key: "research_notes",
        name: "Notes",
        definition: {
          workflows: {
            capture: {
              name: "Capture",
              inputSchema: {
                type: "object",
                properties: {
                  title: { type: "string" },
                  text: { type: "string" },
                },
                required: ["title", "text"],
              },
            },
          },
        },
      },
    ],
  };
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, options?: RequestInit) => {
      if (url.endsWith("/workflow-packages"))
        return new Response(JSON.stringify(packages));
      if (options?.method === "POST" && url.endsWith("/schedules")) {
        submitted.push(JSON.parse(String(options.body)));
        throw new TypeError("connection lost");
      }
      throw new Error(`Unexpected request: ${url}`);
    }),
  );
  render(
    <QueryClientProvider
      client={
        new QueryClient({
          defaultOptions: {
            queries: { retry: false },
            mutations: { retry: false },
          },
        })
      }
    >
      <MemoryRouter
        initialEntries={[
          {
            pathname: "/scheduled-tasks/new",
            state: {
              scheduleInput: {
                packageKey: "research_notes",
                workflowKey: "capture",
                name: "保存会议原文",
                parameters: { title: "会议", text: "原文内容" },
              },
            },
          },
        ]}
      >
        <SchedulePage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
  expect(await screen.findByRole("textbox", { name: "标题" })).toHaveValue(
    "会议",
  );
  expect(screen.getByRole("textbox", { name: "原文" })).toHaveValue("原文内容");
  expect(
    screen.queryByRole("tab", { name: "Advanced JSON" }),
  ).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "启用自动执行" }));
  await waitFor(() => expect(submitted).toHaveLength(1));
  await screen.findByText(/尚未确认新安排是否已生效/);
  expect(screen.getByRole("textbox", { name: "原文" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "启用自动执行" }));
  await waitFor(() => expect(submitted).toHaveLength(2));
  expect(submitted[1]).toEqual(submitted[0]);
  expect(submitted[0].requestId).toEqual(expect.any(String));
  expect(submitted[0].parameters).toEqual({ title: "会议", text: "原文内容" });
});
