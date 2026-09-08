import { describe, expect, it } from "vitest";
import { initialParameters, parseParameters } from "./parameter-values";
import { validateLaunchValueForSchema } from "./schema/launch-input-state";
describe("workflow parameter values", () => {
  it.each([
    ["0", 0],
    ["false", false],
    ["null", null],
    ["[]", []],
    ['""', ""],
    ['["99999999999999999.01"]', ["99999999999999999.01"]],
  ])("preserves JSON root %s", (text, expected) => {
    expect(parseParameters(text as string)).toEqual(expected);
  });
  it("initializes scalar and array schemas without an object wrapper", () => {
    expect(
      initialParameters({ type: "array", items: { type: "string" } }),
    ).toEqual([]);
    expect(initialParameters({ type: "integer" })).toBe(0);
    expect(initialParameters({ type: "boolean" })).toBe(false);
    expect(
      initialParameters({ type: ["string", "null"], default: null }),
    ).toBeNull();
  });
  it("checks root scalar and array item types through the existing schema codec", () => {
    expect(validateLaunchValueForSchema({ type: "integer" }, 7)).toEqual([]);
    expect(validateLaunchValueForSchema({ type: "integer" }, "7")).not.toEqual(
      [],
    );
    expect(
      validateLaunchValueForSchema(
        { type: "array", items: { type: "string" } },
        ["one", "two"],
      ),
    ).toEqual([]);
    expect(
      validateLaunchValueForSchema(
        { type: "array", items: { type: "string" } },
        ["one", 2],
      ),
    ).toEqual([{ field: "parameters.1", issue: "Expected a string." }]);
  });
  it("does not silently replace nonfinite numbers or blank input with null", () => {
    expect(() => parseParameters("1e10000")).toThrow("finite JSON numbers");
    expect(() => parseParameters("")).toThrow("valid JSON");
  });
});
