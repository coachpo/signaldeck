import { render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { ArtifactReading, ResultValue } from "./result-content";

it("renders boolean, null and business-like keys as literal generic values", () => {
  render(<ResultValue value={{ includeRisk: false, collection: null, reportId: 0 }} />);
  for (const text of ["includeRisk", "collection", "reportId", "false", "null", "0"])
    expect(screen.getByText(text, { exact: true })).toBeVisible();
  expect(screen.queryByText("未提供")).not.toBeInTheDocument();
  expect(screen.queryByText("关闭")).not.toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});

const artifactQuery = vi.hoisted(() => vi.fn());
vi.mock("@/hooks/use-workflow-platform", () => ({ useArtifact: artifactQuery }));
it.each([['"# A JSON string"', "# A JSON string"], ['# invalid JSON', '# invalid JSON']])("keeps JSON string and invalid JSON bytes literal: %s", (data, expected) => {
  artifactQuery.mockReturnValue({ data });
  render(<ArtifactReading digest="json" mediaType="application/json" initialOpen />);
  expect(screen.getByText(expected)).toBeVisible();
  expect(screen.queryByRole("heading")).not.toBeInTheDocument();
});
it("renders text attachments with shared Markdown", () => {
  artifactQuery.mockReturnValue({ data: "## 附件标题\n\n1. 清单项目" });
  const { container } = render(<ArtifactReading digest="text" mediaType="text/markdown" initialOpen />);
  expect(screen.getByRole("heading", { name: "附件标题" })).toBeVisible();
  expect(container.querySelector(".markdown-preview ol li")).toHaveTextContent("清单项目");
});


it("uses declared field titles without changing arbitrary business values or source text", () => {
  render(<ResultValue value={{ identifier: "customer supplied id", payload: { flag: false, source: "const schema = { id: 42 };", absent: null } }} schema={{ type: "object", properties: { identifier: { type: "string", title: "客户编号" }, payload: { type: "object", title: "提交内容", properties: { flag: { type: "boolean", title: "包含附件" } } } } }} />);
  expect(screen.getByText("客户编号")).toBeVisible();
  expect(screen.getByText("customer supplied id")).toBeVisible();
  expect(screen.getByText("包含附件")).toBeVisible();
  expect(screen.getByText("false")).toBeVisible();
  expect(screen.getByText("null")).toBeVisible();
  expect(screen.getByText("const schema = { id: 42 };")).toBeVisible();
});
