import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { MarkdownContent } from "./markdown-content";

it("preserves Markdown structure, ordered start, links and keyboard readable overflow", () => {
  const source = "# 标题\n\n正文与 `inline`。\n\n3. 第三项\n4. 第四项\n   - 嵌套项\n\n| 列一 | 列二 |\n| --- | --- |\n| 内容 | 更多 |\n\n```txt\nvery long code\n```\n\n[原始链接](https://example.com/path)";
  const { container } = render(<MarkdownContent>{source}</MarkdownContent>);
  expect(screen.getByRole("heading", { name: "标题", level: 1 })).toBeVisible();
  expect(container.querySelector("ol")).toHaveAttribute("start", "3");
  expect(container.querySelector("ol ul li")).toHaveTextContent("嵌套项");
  expect(screen.getByRole("region", { name: "表格" })).toHaveAttribute("tabindex", "0");
  expect(screen.getByLabelText("代码块")).toHaveAttribute("tabindex", "0");
  expect(screen.getByLabelText("代码块").textContent).toBe("very long code\n");
  expect(screen.getByRole("link", { name: "原始链接" })).toHaveAttribute("href", "https://example.com/path");
});
it("does not enable raw HTML or unsafe links", () => {
  const { container } = render(<MarkdownContent>{"[unsafe](javascript:alert%281%29)\n\n<script>alert(1)</script>"}</MarkdownContent>);
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector("a")).not.toHaveAttribute("href", "javascript:alert%281%29");
});
