import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ErrorBoundaryFallback } from "./error-boundary-fallback";

describe("ErrorBoundaryFallback", () => {
  it("renders app failures through an expanded responsive fallback layout", () => {
    const error = new Error(
      "A very long render failure message should remain readable without squeezing the fallback card into a tiny centered box or forcing one-word-per-line wrapping.",
    );
    const onReset = vi.fn();

    const { container } = render(
      <ErrorBoundaryFallback error={error} onReset={onReset} />,
    );

    const page = container.firstElementChild;
    const content = screen.getByTestId("error-boundary-fallback-content");
    const status = screen.getByTestId("error-boundary-fallback-status");
    const statusStrip = status.querySelector("[role='list']");
    const meta = screen.getByTestId("error-boundary-fallback-meta");
    const panel = screen.getByTestId("error-boundary-fallback-panel");
    const message = screen.getByTestId("error-boundary-fallback-error");

    expect(page).toHaveClass("min-h-screen", "px-4", "py-8");
    expect(content).toHaveClass("w-full", "max-w-6xl", "flex-col", "gap-6");
    expect(status).toHaveClass("w-full", "min-w-0");
    expect(statusStrip).toHaveClass(
      "w-full",
      "max-w-none",
      "justify-start",
      "flex-wrap",
    );
    expect(meta).toHaveClass("w-full", "min-w-0", "flex-wrap", "gap-2");
    expect(panel).toHaveClass("w-full", "max-w-none");
    expect(message).toHaveClass("w-full", "max-w-4xl", "break-words");
    expect(screen.queryByText(error.message)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重试打开" })).toBeVisible();
    expect(screen.getByRole("button", { name: "重新加载" })).toBeVisible();
  });
});
