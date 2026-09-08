import { describe, expect, it } from "vitest";
import { queryKeys } from "./query-keys";
describe("query scopes", () => {
  it("isolates resource families and keeps detail/list under one invalidation scope", () => {
    const groups = Object.entries(queryKeys.platform)
      .filter(([name]) => name !== "all")
      .map(([, v]) => v as typeof queryKeys.platform.runs);
    expect(new Set(groups.map((g) => JSON.stringify(g.all))).size).toBe(
      groups.length,
    );
    for (const group of groups) {
      expect(group.list().slice(0, group.all.length)).toEqual(group.all);
      expect(group.detail("a/b").slice(0, group.all.length)).toEqual(group.all);
      expect(group.detail("a/b")).not.toEqual(group.detail("a%2Fb"));
    }
  });
});
