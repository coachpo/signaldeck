import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { ResultHistoryPage } from "./result-history";
import { packageFixture, runFixture } from "./fixtures";
function response(value: unknown) { return new Response(JSON.stringify(value), { headers: { "content-type": "application/json" } }); }
afterEach(() => vi.unstubAllGlobals());
it("loads package choices and preserves history context through a personal mark", async () => {
  let favorite = false;
  const patches: object[] = [];
  const queries: string[] = [];
  const metadata = () => ({ runId: "run-1", revision: favorite ? 1 : 0, isFavorite: favorite, isRead: false, note: "", updatedAt: null });
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    if (url.endsWith("/workflow-packages")) return response({ items: [packageFixture] });
    if (options?.method === "PATCH") { patches.push(JSON.parse(options.body as string)); favorite = true; return response(metadata()); }
    queries.push(url);
    return response({ items: [{ ...runFixture, status: "succeeded", title: "已存结果", metadata: metadata() }], total: 60, offset: 25, limit: 25, snapshotAt: "2026-09-10T09:00:00Z" });
  }));
  const router = createMemoryRouter([{ path: "/runs", element: <ResultHistoryPage /> }], { initialEntries: ["/runs?q=资料&offset=25&isRead=false&snapshotAt=2026-09-10T09%3A00%3A00Z"] });
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><RouterProvider router={router} /></QueryClientProvider>);
  expect(await screen.findByRole("option", { name: packageFixture.definition.workflows.main.name })).toBeInTheDocument();
  fireEvent.click(await screen.findByRole("button", { name: "收藏 已存结果" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "取消收藏 已存结果" })).toBeEnabled());
  expect(patches).toEqual([{ expectedRevision: 0, isFavorite: true }]);
  const current = new URLSearchParams(router.state.location.search);
  expect(current.get("offset")).toBe("25");
  expect(current.get("q")).toBe("资料");
  expect(current.get("isRead")).toBe("false");
  expect(queries.length).toBeGreaterThanOrEqual(2);
  fireEvent.change(screen.getByRole("combobox", { name: "收藏筛选" }), { target: { value: "true" } });
  await waitFor(() => expect(new URLSearchParams(router.state.location.search).get("isFavorite")).toBe("true"));
  expect(new URLSearchParams(router.state.location.search).has("offset")).toBe(false);
});
