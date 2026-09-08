import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ThemeProvider } from "./components/theme-provider";
import { router } from "./routes";

Object.defineProperty(globalThis, "localStorage", {
  configurable: true,
  value: {
    getItem: () => null,
    removeItem: () => undefined,
    setItem: () => undefined,
  },
});

type RouteWithHandle = {
  handle?: unknown;
  index?: boolean;
  path?: string;
  lazy?: () => Promise<unknown>;
};

type RouteHandle = {
  pattern: string;
  testId: string;
};

function childRoutes(): readonly RouteWithHandle[] {
  const root = router.routes.find((route) => route.path === "/");
  return (root?.children ?? []) as readonly RouteWithHandle[];
}

function routeEntry(pattern: string): string {
  if (pattern === "*") {
    return "/does-not-exist";
  }

  return pattern.replace(/:([A-Za-z0-9_]+)/g, (_match, param: string) => {
    return (
      {
        packageId: "example",
        runId: "run-example",
        scheduleId: "schedule-example",
      }[param] ?? "1"
    );
  });
}

function renderRoute(entry: string) {
  const testRouter = createMemoryRouter(router.routes, {
    initialEntries: [entry],
  });

  return render(
    <ThemeProvider>
      <QueryClientProvider
        client={
          new QueryClient({
            defaultOptions: { queries: { retry: false } },
          })
        }
      >
        <RouterProvider router={testRouter} />
      </QueryClientProvider>
    </ThemeProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockImplementation(
        async () =>
          new Response(
            JSON.stringify({
              code: "test_unavailable",
              message: "Fixture API unavailable",
              details: [],
            }),
            { status: 503, headers: { "content-type": "application/json" } },
          ),
      ),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("router", () => {
  it("renders every registered route without crashing", async () => {
    for (const route of childRoutes()) {
      const handle = route.handle as RouteHandle | undefined;

      expect(
        handle,
        `Missing handle for ${route.path ?? "index"}`,
      ).toBeDefined();
      await route.lazy?.();
      const view = renderRoute(routeEntry(handle?.pattern ?? "*"));

      expect(await screen.findByTestId(handle?.testId ?? "")).toBeVisible();
      view.unmount();
    }
  });
});
