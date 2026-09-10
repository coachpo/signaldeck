import { describe, expect, it } from "vitest";
import { queryKeys } from "./query-keys";
describe("query scopes", () => {
  it("isolates resource families and keeps detail/list under one invalidation scope", () => {
    const groups = Object.entries(queryKeys.platform)
      .filter(([name]) => !["all", "modelUsage", "attention"].includes(name))
      .map(([, v]) => v as typeof queryKeys.platform.runs);
    expect(new Set(groups.map((g) => JSON.stringify(g.all))).size).toBe(
      groups.length,
    );
    expect(queryKeys.platform.modelUsage.all).not.toEqual(queryKeys.platform.attention.all);
    for (const group of groups) {
      expect(group.list().slice(0, group.all.length)).toEqual(group.all);
      expect(group.detail("a/b").slice(0, group.all.length)).toEqual(group.all);
      expect(group.detail("a/b")).not.toEqual(group.detail("a%2Fb"));
    }
  });
  it("keeps usage windows and execution update filters distinct within their scopes", () => {
    const usage = queryKeys.platform.modelUsage;
    const samples = [usage.run("a/b"), usage.run("a%2Fb"), usage.day("2026-09-10", "UTC"), usage.day("2026-09-10", "Europe/Helsinki")];
    for (const sample of samples) expect(sample.slice(0, usage.all.length)).toEqual(usage.all);
    expect(new Set(samples.map((sample) => JSON.stringify(sample))).size).toBe(samples.length);
    const updates = queryKeys.platform.attention;
    const all = updates.list({ view: "all" }), unread = updates.list({ view: "attention" });
    expect(all.slice(0, updates.all.length)).toEqual(updates.all);
    expect(unread.slice(0, updates.all.length)).toEqual(updates.all);
    expect(all).not.toEqual(unread);
    const scopes = Object.values(queryKeys.platform).filter((value) => !Array.isArray(value)).map((value) => JSON.stringify((value as { all: readonly string[] }).all));
    expect(new Set(scopes).size).toBe(scopes.length);
  });
});
