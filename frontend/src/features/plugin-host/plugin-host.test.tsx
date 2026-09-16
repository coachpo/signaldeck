import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, Link, Outlet, RouterProvider } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { ThemeProvider } from "@/components/theme-provider";
import { storeExpert, storeTheme } from "@/lib/display-preferences";
import { queryKeys } from "@/lib/query-keys";
import type { PluginPage } from "@/lib/api/plugin-pages";
import { PluginHost } from "./plugin-host";
import { localPath, ownedPluginUrl, PLUGIN_UI_PROTOCOL } from "./navigation";

const page: PluginPage = { mountKey: "third-v1", pluginId: "third", artifactDigest: "sha256:third", title: "访谈", pageUrl: "/apps/third-v1/", enabled: true };
function setup(path = "/apps/third-v1/detail/123?view=full#summary") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
  client.setQueryData(queryKeys.platform.plugins.pages(), [page]);
  const router = createMemoryRouter([{
    path: "/", Component: () => <><PluginHost /><Link to="/runs/source?tab=result">查看结果</Link><Link to="/apps/third-v1/" data-plugin-resume="true">访谈</Link><Outlet /></>,
    children: [{ path: "apps/:mountKey/*", Component: () => null }, { path: "runs/:id", Component: () => <a href="/apps/third-v1/detail/456?mode=edit">打开详情</a> }],
  }], { initialEntries: [path] });
  render(<ThemeProvider><QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider></ThemeProvider>);
  return { client, router };
}
function message(frame: HTMLIFrameElement, data: object, overrides: Partial<MessageEventInit> = {}) {
  fireEvent(window, new MessageEvent("message", { origin: window.location.origin, source: frame.contentWindow, data: { protocol: PLUGIN_UI_PROTOCOL, ...data }, ...overrides }));
}

describe("generic plugin host", () => {
  it("boots a deep route through the mounted root and delegates its full location", async () => {
    setup();
    const frame = await screen.findByTitle<HTMLIFrameElement>("访谈");
    expect(frame.src).toBe(`${window.location.origin}/_plugins/third-v1/?embedded=1`);
    expect(frame).not.toBeVisible();
    expect(screen.getByRole("status")).toHaveTextContent("正在打开页面");
    const send = vi.spyOn(frame.contentWindow!, "postMessage");
    message(frame, { type: "ready" });
    expect(frame).toBeVisible();
    await waitFor(() => expect(send).toHaveBeenCalledWith({ protocol: PLUGIN_UI_PROTOCOL, type: "location", path: "/detail/123?view=full#summary" }, window.location.origin));
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
    act(() => { storeTheme("dark"); storeExpert(true); });
    await waitFor(() => expect(send).toHaveBeenCalledWith({ protocol: PLUGIN_UI_PROTOCOL, type: "preferences", theme: "dark", expertMode: true }, window.location.origin));
    act(() => { storeTheme("system"); storeExpert(false); });
  });

  it("resends the current location and preferences on a repeated child handshake", async () => {
    setup();
    const frame = await screen.findByTitle<HTMLIFrameElement>("访谈");
    const send = vi.spyOn(frame.contentWindow!, "postMessage");
    message(frame, { type: "ready" });
    await waitFor(() => expect(send).toHaveBeenCalledWith({ protocol: PLUGIN_UI_PROTOCOL, type: "location", path: "/detail/123?view=full#summary" }, window.location.origin));
    send.mockClear();
    message(frame, { type: "ready" });
    await waitFor(() => expect(send).toHaveBeenCalledWith({ protocol: PLUGIN_UI_PROTOCOL, type: "location", path: "/detail/123?view=full#summary" }, window.location.origin));
    expect(send).toHaveBeenCalledWith(expect.objectContaining({ protocol: PLUGIN_UI_PROTOCOL, type: "preferences" }), window.location.origin);
    expect(screen.getByTitle("访谈")).toBe(frame);
  });

  it("retains the iframe and dirty memory through result navigation, disablement and upgrades", async () => {
    const { client, router } = setup();
    const frame = await screen.findByTitle<HTMLIFrameElement>("访谈");
    message(frame, { type: "ready" });
    message(frame, { type: "state", dirty: true, busy: false });
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);
    fireEvent.click(screen.getByRole("link", { name: "查看结果" }));
    expect(await screen.findByRole("link", { name: "打开详情" })).toBeVisible();
    expect(screen.getByTitle("访谈")).toBe(frame);
    act(() => client.setQueryData(queryKeys.platform.plugins.pages(), [{ ...page, enabled: false }, { ...page, mountKey: "third-v2", artifactDigest: "sha256:new" }]));
    fireEvent.click(screen.getByRole("link", { name: "打开详情" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/apps/third-v1/detail/456"));
    expect(screen.getByTitle("访谈")).toBe(frame);
    expect(screen.getByRole("link", { name: "返回来源结果" })).toHaveAttribute("href", "/runs/source?tab=result");
  });

  it("resumes the last deep page when returning through the sidebar", async () => {
    const { router } = setup();
    const frame = await screen.findByTitle<HTMLIFrameElement>("访谈");
    fireEvent.click(screen.getByRole("link", { name: "查看结果" }));
    await screen.findByRole("link", { name: "打开详情" });
    fireEvent.click(screen.getByRole("link", { name: "访谈" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/apps/third-v1/detail/123"));
    expect(router.state.location.search).toBe("?view=full");
    expect(router.state.location.hash).toBe("#summary");
    expect(screen.getByTitle("访谈")).toBe(frame);
  });

  it("keeps navigation in the host while the catalog has no available mount", async () => {
    const { client, router } = setup("/runs/source?tab=result");
    act(() => client.setQueryData(queryKeys.platform.plugins.pages(), []));
    fireEvent.click(screen.getByRole("link", { name: "打开详情" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/apps/third-v1/detail/456"));
    expect(screen.getByText("页面暂时无法打开")).toBeVisible();
    expect(screen.queryByTitle("访谈")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "查看结果" })).toBeVisible();
  });

  it("lets the parent own navigation and back/forward without reloading the child", async () => {
    const { router } = setup();
    const frame = await screen.findByTitle<HTMLIFrameElement>("访谈");
    const original = frame.src;
    const send = vi.spyOn(frame.contentWindow!, "postMessage");
    message(frame, { type: "ready" });
    message(frame, { type: "navigate", path: "/detail/other?edit=1" });
    await waitFor(() => expect(router.state.location.pathname).toBe("/apps/third-v1/detail/other"));
    await act(() => router.navigate(-1));
    expect(router.state.location.pathname).toBe("/apps/third-v1/detail/123");
    expect(send).toHaveBeenLastCalledWith({ protocol: PLUGIN_UI_PROTOCOL, type: "location", path: "/detail/123?view=full#summary" }, window.location.origin);
    await act(() => router.navigate(1));
    expect(frame.src).toBe(original);
    expect(screen.getByTitle("访谈")).toBe(frame);
  });

  it("rejects foreign windows, origins, extra fields and mount-escaping navigation", async () => {
    const { router } = setup();
    const frame = await screen.findByTitle<HTMLIFrameElement>("访谈");
    for (const overrides of [{ origin: "https://foreign.example" }, { source: window }]) message(frame, { type: "navigate", path: "/bad" }, overrides);
    for (const path of ["//foreign.example", "/../api", "/%2e%2e/api", "/\\foreign.example"]) message(frame, { type: "navigate", path });
    message(frame, { type: "navigate", path: "/bad", body: "private" });
    message(frame, { type: "navigate", path: "/settings", target: "platform" });
    expect(router.state.location.pathname).toBe("/apps/third-v1/detail/123");
    message(frame, { type: "state", dirty: true });
    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(false);
  });

  it("offers recovery for an offline child while preserving host navigation", async () => {
    vi.useFakeTimers();
    setup();
    const frame = screen.getByTitle<HTMLIFrameElement>("访谈");
    act(() => vi.advanceTimersByTime(15_000));
    vi.useRealTimers();
    expect(screen.getByText("页面暂时无法打开")).toBeVisible();
    expect(screen.getByRole("link", { name: "查看结果" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "重试" }));
    expect(screen.getByTitle("访谈")).not.toBe(frame);
  });

  it("recognizes same-origin host routes and validates local paths", () => {
    expect(ownedPluginUrl("/apps/third-v1/custom?x=1")).toBe("/apps/third-v1/custom?x=1");
    expect(ownedPluginUrl("https://external.example/apps/third-v1/")).toBeNull();
    expect(ownedPluginUrl("/apps/unknown/")).toBe("/apps/unknown/");
    expect(localPath("/detail?id=123#body")).toBe(true);
    expect(localPath("/a/../api")).toBe(false);
  });
});
