import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { RouteErrorPage } from "./route-error";

const { isRouteErrorResponseMock, routeErrorMock } = vi.hoisted(() => ({
  isRouteErrorResponseMock: vi.fn(),
  routeErrorMock: vi.fn(),
}));

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
  isRouteErrorResponse: (error: unknown) => isRouteErrorResponseMock(error),
  useRouteError: () => routeErrorMock(),
}));

describe("RouteErrorPage", () => {
  beforeEach(() => {
    isRouteErrorResponseMock.mockReset();
    routeErrorMock.mockReset();
    isRouteErrorResponseMock.mockReturnValue(false);
  });

  it("renders unexpected render failures through a readable responsive error layout", () => {
    routeErrorMock.mockReturnValue(new Error("Route harness failure"));

    render(<RouteErrorPage />);

    const page = screen.getByTestId("route-error-page");
    const content = screen.getByTestId("route-error-content");
    const status = screen.getByTestId("route-error-status");
    const statusStrip = status.querySelector("[role='list']");
    const errorCard = screen
      .getByText("继续处理任务")
      .closest("[data-slot='card']");

    expect(page).toBeVisible();
    expect(page).toHaveClass("min-h-screen", "px-4", "py-8", "sm:py-10");
    expect(content).toHaveClass("w-full", "max-w-6xl", "flex-col", "gap-6");
    expect(
      screen.getByRole("heading", { level: 1, name: "暂时无法打开页面" }),
    ).toBeVisible();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByTestId("route-error-description")).toHaveClass(
      "max-w-4xl",
      "leading-6",
    );
    expect(status).toHaveClass("w-full", "min-w-0");
    expect(
      status.closest("[data-slot='page-context-actions']"),
    ).not.toBeInTheDocument();
    expect(statusStrip).toHaveClass(
      "w-full",
      "max-w-none",
      "justify-start",
      "flex-wrap",
    );
    expect(screen.getByTestId("route-error-meta")).toHaveClass(
      "w-full",
      "flex-wrap",
      "gap-2",
    );
    expect(errorCard).toHaveClass("w-full", "max-w-none");
    expect(
      screen.getByText(
        "可以重新加载此页；若仍无法打开，请返回首页。正在执行的任务不受页面关闭影响。",
      ),
    ).toBeVisible();
    expect(screen.getByText("继续处理任务")).toBeVisible();
    expect(screen.getByText("页面暂时无法打开")).toBeVisible();
    expect(screen.queryByText("Route harness failure")).not.toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "返回任务首页" }),
    ).toHaveAttribute("href", "/");
  });

  it("renders route response failures without the default router error UI", () => {
    const routeResponse = { status: 404, statusText: "Not Found" };
    routeErrorMock.mockReturnValue(routeResponse);
    isRouteErrorResponseMock.mockImplementation((error) => error === routeResponse);

    render(<RouteErrorPage />);

    expect(
      screen.getByRole("heading", { level: 1, name: "找不到这项内容" }),
    ).toBeVisible();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByText("内容不可用")).toBeVisible();
    expect(
      screen.queryByText("Unexpected Application Error!"),
    ).not.toBeInTheDocument();
  });
});
