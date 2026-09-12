import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
import { LaunchInputs } from "./launch-inputs";

function Form({ schema, initial }: { schema: JsonObject; initial: Json }) {
  const [value, setValue] = useState(initial);
  return (
    <>
      <LaunchInputs
        schema={schema}
        value={value}
        onChange={setValue}
        onDirtyChange={() => {}}
      />
      <output>{JSON.stringify(value)}</output>
    </>
  );
}

it("edits scalar input directly and reports recoverable integer errors without truncation", () => {
  render(<Form schema={{ type: "integer", title: "份数" }} initial={0} />);
  expect(screen.queryByRole("tab")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("份数"), { target: { value: "2.5" } });
  expect(screen.getByRole("status")).toHaveTextContent("2.5");
  expect(screen.getByRole("alert")).toHaveTextContent("请填写整数。");
  fireEvent.change(screen.getByLabelText("份数"), { target: { value: "7" } });
  expect(screen.getByRole("status")).toHaveTextContent("7");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("edits array and null roots without inventing an object wrapper", () => {
  const view = render(
    <Form
      schema={{ type: "array", items: { type: "string" } }}
      initial={["first,exact"]}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "添加项目" }));
  fireEvent.change(screen.getByLabelText("第 2 项"), {
    target: { value: "second" },
  });
  expect(JSON.parse(screen.getByRole("status").textContent!)).toEqual([
    "first,exact",
    "second",
  ]);
  view.unmount();
  render(<Form schema={{ type: "null" }} initial={null} />);
  expect(screen.getByText("此项为空值，无需填写。")).toBeVisible();
  expect(screen.getByRole("status")).toHaveTextContent("null");
});

it("preserves input and declared business labels when switching display modes", () => {
  const props = {
    schema: {
      type: "object",
      properties: {
        raw: { type: "string", title: "原文", description: "保留提供的内容" },
      },
      required: ["raw"],
    },
    value: { raw: "  原文\n" },
    onChange: vi.fn(),
    onDirtyChange: vi.fn(),
  };
  const view = render(<LaunchInputs {...props} technical={false} />);
  expect(screen.getByLabelText("原文")).toHaveValue("  原文\n");
  view.rerender(<LaunchInputs {...props} technical />);
  expect(screen.getByLabelText("原文")).toHaveValue("  原文\n");
  for (const text of ["JSON", "root", "object", "string", "raw", "required"])
    expect(screen.queryByText(text)).not.toBeInTheDocument();
  expect(screen.getByText("保留提供的内容")).toBeVisible();
  expect(props.onChange).not.toHaveBeenCalled();
});

it("recovers valid unapplied drafts only after an explicit restore action", () => {
  const change = vi.fn();
  const textChange = vi.fn();
  render(
    <LaunchInputs
      schema={{ type: "array", items: { type: "string" } }}
      value={["saved"]}
      initialJsonText={'["  draft\\n","second"]'}
      onJsonTextChange={textChange}
      onChange={change}
      onDirtyChange={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("第 1 项")).toBeDisabled();
  expect(change).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "恢复未完成输入" }));
  expect(change).toHaveBeenCalledWith(["  draft\n", "second"]);
  expect(textChange).toHaveBeenCalledWith(null);
});

it("retains incomplete originals with download and explicit discard, preserving applied values", () => {
  const change = vi.fn();
  const textChange = vi.fn();
  const dirty = vi.fn();
  const unfinished = '  {"renamed": [\n';
  const view = render(
    <LaunchInputs
      schema={{
        type: "object",
        properties: { renamed: { type: "string", title: "标题" } },
      }}
      value={{ renamed: "applied" }}
      initialJsonText={unfinished}
      onJsonTextChange={textChange}
      onChange={change}
      onDirtyChange={dirty}
    />,
  );
  expect(screen.getByText("发现未完成的输入修改")).toBeVisible();
  expect(
    screen.getByRole("button", { name: "下载未完成输入原稿" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "恢复未完成输入" }),
  ).not.toBeInTheDocument();
  expect(screen.getByLabelText("标题")).toHaveValue("applied");
  expect(screen.getByLabelText("标题")).toBeDisabled();
  expect(dirty).toHaveBeenLastCalledWith(true);
  expect(textChange).not.toHaveBeenCalled();
  view.rerender(
    <LaunchInputs
      technical={false}
      schema={{
        type: "object",
        properties: { renamed: { type: "string", title: "标题" } },
      }}
      value={{ renamed: "applied" }}
      initialJsonText={unfinished}
      onJsonTextChange={textChange}
      onChange={change}
      onDirtyChange={dirty}
    />,
  );
  fireEvent.click(
    screen.getByRole("button", { name: "保留已确认内容，放弃未完成修改" }),
  );
  expect(textChange).toHaveBeenLastCalledWith(null);
  expect(dirty).toHaveBeenLastCalledWith(false);
  expect(screen.getByLabelText("标题")).not.toBeDisabled();
  expect(change).not.toHaveBeenCalled();
});

it("blocks incomplete fields with their declared titles and repairs them in place", () => {
  const dirty = vi.fn();
  const change = vi.fn();
  const props = {
    schema: {
      type: "object",
      properties: { title: { type: "string", title: "标题", minLength: 1 } },
      required: ["title"],
    },
    onChange: change,
    onDirtyChange: dirty,
  };
  const view = render(<LaunchInputs {...props} value={{ title: "" }} />);
  expect(screen.getByRole("alert")).toHaveTextContent("请至少填写 1 个字符。");
  expect(dirty).toHaveBeenLastCalledWith(true);
  view.rerender(<LaunchInputs {...props} value={{ title: "已填写" }} />);
  expect(dirty).toHaveBeenLastCalledWith(false);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

it("downloads an unfinished original verbatim without clearing it", async () => {
  const original = '  {"amount": "99999999999999999.01",\n';
  const textChange = vi.fn();
  let downloaded: Blob | undefined;
  vi.stubGlobal(
    "URL",
    class extends URL {
      static createObjectURL(blob: Blob) {
        downloaded = blob;
        return "blob:original";
      }
      static revokeObjectURL = vi.fn();
    },
  );
  const click = vi
    .spyOn(HTMLAnchorElement.prototype, "click")
    .mockImplementation(() => {});
  try {
    render(
      <LaunchInputs
        schema={{ type: "null" }}
        value={null}
        onChange={vi.fn()}
        onDirtyChange={vi.fn()}
        initialJsonText={original}
        onJsonTextChange={textChange}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "下载未完成输入原稿" }));
    const content = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result));
      reader.onerror = reject;
      reader.readAsText(downloaded!);
    });
    expect(content).toBe(original);
    expect(textChange).not.toHaveBeenCalled();
    expect(screen.getByText("发现未完成的输入修改")).toBeVisible();
  } finally {
    click.mockRestore();
    vi.unstubAllGlobals();
  }
});
