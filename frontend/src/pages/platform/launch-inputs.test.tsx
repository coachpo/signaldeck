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

it("presents ordinary input labels without schema chrome and preserves JSON drafts across mode changes", () => {
  const props = { schema: { type: "object", properties: { raw: {type: "string", title: "原文", description: "保留提供的内容"} }, required: ["raw"] }, value: {raw:"saved"}, onChange: vi.fn(), onDirtyChange: vi.fn() };
  const view = render(<LaunchInputs {...props} technical={false} />);
  expect(screen.getByRole("tab", {name:"填写输入"})).toBeVisible();
  expect(screen.getByText("任务输入")).toBeVisible();
  expect(screen.getByLabelText("原文")).toHaveValue("saved");
  expect(screen.getByText("保留提供的内容")).toBeVisible();
  for (const label of ["Workflow parameters", "string", "object", "root", "raw", "Enter a value.", "Enter the fields below."]) expect(screen.queryByText(label)).not.toBeInTheDocument();
  expect(screen.getAllByText("必填").length).toBeGreaterThan(0);
  fireEvent.mouseDown(screen.getByRole("tab", {name:"JSON 输入"}),{button:0,ctrlKey:false});
  fireEvent.change(screen.getByLabelText("任务输入 JSON"),{target:{value:'{"raw":"unfinished"'}});
  view.rerender(<LaunchInputs {...props} technical />);
  expect(screen.getByLabelText("Parameters JSON")).toHaveValue('{"raw":"unfinished"');
  view.rerender(<LaunchInputs {...props} technical={false} />);
  expect(screen.getByLabelText("任务输入 JSON")).toHaveValue('{"raw":"unfinished"');
  fireEvent.click(screen.getByRole("button", {name:"放弃 JSON 修改"}));
  expect(screen.getByLabelText("任务输入 JSON")).toHaveValue(JSON.stringify(props.value,null,2));
  expect(props.onChange).not.toHaveBeenCalled();
  expect(props.onDirtyChange).toHaveBeenLastCalledWith(false);
});
