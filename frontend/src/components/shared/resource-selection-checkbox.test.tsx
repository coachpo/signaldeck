import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ResourceSelectionCheckbox } from "./resource-selection-checkbox";

describe("ResourceSelectionCheckbox", () => {
  it("maps aggregate selection state to checked, mixed, and unchecked values", () => {
    const { rerender } = render(
      <ResourceSelectionCheckbox
        ariaLabel="Select all shown reports"
        indeterminate
        selected
        onSelectedChange={() => {}}
      />,
    );

    expect(
      screen.getByRole("checkbox", { name: "Select all shown reports" }),
    ).toHaveAttribute("aria-checked", "true");

    rerender(
      <ResourceSelectionCheckbox
        ariaLabel="Select all shown reports"
        indeterminate
        selected={false}
        onSelectedChange={() => {}}
      />,
    );

    expect(
      screen.getByRole("checkbox", { name: "Select all shown reports" }),
    ).toHaveAttribute("aria-checked", "mixed");

    rerender(
      <ResourceSelectionCheckbox
        ariaLabel="Select all shown reports"
        selected={false}
        onSelectedChange={() => {}}
      />,
    );

    expect(
      screen.getByRole("checkbox", { name: "Select all shown reports" }),
    ).toHaveAttribute("aria-checked", "false");
  });

  it("converts checked-state changes back to booleans for callers", () => {
    const onSelectedChange = vi.fn();

    render(
      <ResourceSelectionCheckbox
        ariaLabel="Select template"
        selected={false}
        onSelectedChange={onSelectedChange}
      />,
    );

    fireEvent.click(screen.getByRole("checkbox", { name: "Select template" }));

    expect(onSelectedChange).toHaveBeenCalledWith(true);
  });
});
