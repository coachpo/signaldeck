import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { ResultValue } from "./result-content";

it("renders boolean, null and business-like keys as literal generic values", () => {
  render(<ResultValue value={{ includeRisk: false, collection: null, reportId: 0 }} />);
  for (const text of ["includeRisk", "collection", "reportId", "false", "null", "0"])
    expect(screen.getByText(text, { exact: true })).toBeVisible();
  expect(screen.queryByText("未提供")).not.toBeInTheDocument();
  expect(screen.queryByText("关闭")).not.toBeInTheDocument();
  expect(screen.queryByRole("link")).not.toBeInTheDocument();
});
