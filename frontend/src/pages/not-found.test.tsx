import type { ComponentProps } from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { NotFoundPage } from "./not-found";

vi.mock("react-router", () => ({
  Link: ({ children, to, ...props }: ComponentProps<"a"> & { to: string }) => (
    <a href={to} {...props}>
      {children}
    </a>
  ),
}));

describe("NotFoundPage", () => {
  it("renders the product-owned route fallback through a responsive full-page layout", () => {
    render(<NotFoundPage />);

    const page = screen.getByTestId("not-found-page");
    const content = screen.getByTestId("not-found-content");
    const status = screen.getByTestId("not-found-status");
    const statusStrip = status.querySelector("[role='list']");
    const emptyStateCard = screen
      .getByText("继续使用 SignalDeck")
      .closest("[data-slot='card']");

    expect(page).toBeVisible();
    expect(page).toHaveClass("min-h-[calc(100vh-3rem)]", "px-4", "py-8");
    expect(content).toHaveClass("w-full", "max-w-6xl", "flex-col", "gap-6");
    expect(
      screen.getByRole("heading", { level: 1, name: "找不到页面" }),
    ).toBeVisible();
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByTestId("not-found-description")).toHaveClass(
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
    expect(screen.getByTestId("not-found-meta")).toHaveClass(
      "w-full",
      "flex-wrap",
      "gap-2",
    );
    expect(emptyStateCard).toHaveClass("w-full", "max-w-none");
    expect(screen.getByText("继续使用 SignalDeck")).toBeVisible();
    expect(screen.getByText("页面不可用")).toBeVisible();
    expect(screen.queryByText(/route metadata|catch-all|Shell/i)).not.toBeInTheDocument();
    expect(screen.getByText("链接可能已失效，或这项内容已经移除。")).toBeVisible();
    expect(
      screen.getByRole("link", { name: "返回任务首页" }),
    ).toHaveAttribute("href", "/");
  });
});
