import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PageContextBar } from "./page-context-bar";
import { WorkspacePageShell } from "./workspace-page-shell";

describe("WorkspacePageShell", () => {
  it("places sticky context, optional rail, and scroll body in shell-owned regions", () => {
    render(
      <WorkspacePageShell
        bodyAriaLabel="Authoring workspace"
        contextBar={<PageContextBar title="Workspace context" />}
        leftRail={<div>Mode rail</div>}
      >
        <div data-testid="consumer-split-content">Consumer split content</div>
      </WorkspacePageShell>,
    );

    const shell = screen.getByTestId("workspace-page-shell");
    const context = screen.getByTestId("workspace-page-shell-context");
    const content = screen.getByTestId("workspace-page-shell-content");
    const rail = screen.getByTestId("workspace-page-shell-left-rail");
    const body = screen.getByTestId("workspace-page-shell-body");

    expect(shell).toHaveClass("h-full", "min-h-0", "overflow-hidden");
    expect(context).toHaveClass("sticky", "top-0", "shrink-0");
    expect(content).toHaveClass("min-h-0", "flex-1", "overflow-hidden");
    expect(rail).toHaveAttribute("aria-label", "Workspace navigation");
    expect(body).toHaveAttribute("aria-label", "Authoring workspace");
    expect(body).toHaveClass("min-h-0", "flex-1", "overflow-auto");
    expect(
      Array.from(shell.querySelectorAll("[data-workspace-shell-region]")).map(
        (region) => region.getAttribute("data-workspace-shell-region"),
      ),
    ).toEqual(["context", "content", "left-rail", "body"]);
    expect(
      context.compareDocumentPosition(content) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      rail.compareDocumentPosition(body) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(rail).not.toContainElement(
      screen.getByTestId("consumer-split-content"),
    );
    expect(body).toContainElement(screen.getByTestId("consumer-split-content"));
  });

  it("renders without a left rail and keeps body as the only content region", () => {
    render(
      <WorkspacePageShell
        contextBar={<PageContextBar title="Import context" />}
      >
        <p>Single workspace body</p>
      </WorkspacePageShell>,
    );

    const content = screen.getByTestId("workspace-page-shell-content");
    const body = screen.getByTestId("workspace-page-shell-body");

    expect(
      screen.queryByTestId("workspace-page-shell-left-rail"),
    ).not.toBeInTheDocument();
    expect(content).toContainElement(body);
    expect(body).toHaveTextContent("Single workspace body");
  });
});
