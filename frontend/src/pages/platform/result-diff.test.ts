import { expect, it } from "vitest";
import { compareText } from "./result-diff";

it.each([
  ["", ""], ["a\n", "a"], ["a\nb\nc\n", "a\nx\nc\n"], ["a\na\n", "a\nb\na\n"], ["", "a\n"],
])("preserves both exact inputs in deterministic differences", (left, right) => {
  const result = compareText(left, right);
  expect(result.blocks.filter((b) => b.kind !== "added").map((b) => b.text).join("")).toBe(left);
  expect(result.blocks.filter((b) => b.kind !== "removed").map((b) => b.text).join("")).toBe(right);
  expect(compareText(left, right)).toEqual(result);
});
it("bounds large comparisons without truncating either source", () => {
  const left = "old\n".repeat(2000), right = "new\n".repeat(2000);
  expect(compareText(left, right)).toEqual({ coarse: true, blocks: [{ kind: "removed", text: left }, { kind: "added", text: right }] });
});
