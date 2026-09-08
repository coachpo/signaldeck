import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { LaunchInputs } from "./launch-inputs";
it("offers scalar JSON input and validates its type without inventing a parameter object", () => {
  const change = vi.fn();
  render(
    <LaunchInputs
      schema={{ type: "integer" }}
      value={0}
      onChange={change}
      onDirtyChange={vi.fn()}
    />,
  );
  expect(screen.getByRole("tab", { name: "Input form" })).toBeDisabled();
  expect(screen.getByLabelText("Parameters JSON")).toHaveValue("0");
  fireEvent.change(screen.getByLabelText("Parameters JSON"), {
    target: { value: '"wrong"' },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Apply parameters JSON" }),
  );
  expect(screen.getByText("parameters: Expected an integer.")).toHaveAttribute(
    "role",
    "alert",
  );
  expect(change).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText("Parameters JSON"), {
    target: { value: "7" },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Apply parameters JSON" }),
  );
  expect(change).toHaveBeenCalledWith(7);
});
it("applies array parameters exactly as edited", () => {
  const change = vi.fn();
  render(
    <LaunchInputs
      schema={{ type: "array", items: { type: "string" } }}
      value={[]}
      onChange={change}
      onDirtyChange={vi.fn()}
    />,
  );
  fireEvent.change(screen.getByLabelText("Parameters JSON"), {
    target: { value: '["first","second"]' },
  });
  fireEvent.click(
    screen.getByRole("button", { name: "Apply parameters JSON" }),
  );
  expect(change).toHaveBeenCalledWith(["first", "second"]);
});
