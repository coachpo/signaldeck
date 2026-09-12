import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { RecordedCondition, RecordedMapping } from "./result-rules";
const sources = [{ value: "workflow.input", label: "用户填写的信息", schema: { type: "object", properties: { included: { type: "boolean", title: "包含附录" } } } }];
it("explains frozen conditions with field titles and preserves literal values", () => {
  render(<RecordedCondition sources={sources} value={{ op: "all", args: [
    { op: "eq", args: [{ ref: "workflow.input.included" }, { value: false }] },
    { op: "exists", args: [{ ref: "workflow.input" }] },
  ] }} />);
  expect(screen.getByText("同时满足全部条件")).toBeVisible();
  expect(screen.getByText("等于")).toBeVisible();
  expect(screen.getByText("用户填写的信息 › 包含附录")).toBeVisible();
  expect(screen.getByText("false")).toBeVisible();
  expect(document.body.textContent).not.toContain("workflow.input");
});
it("keeps nested fixed source code unchanged when showing mapping fallbacks", () => {
  render(<RecordedMapping sources={sources} value={{ ref: "workflow.input.included", onMissing: { value: "const schema = { operationId: 'user value' };" } }} />);
  expect(screen.getByText("未提供时使用：")).toBeVisible();
  expect(screen.getByText("const schema = { operationId: 'user value' };")).toBeVisible();
});
