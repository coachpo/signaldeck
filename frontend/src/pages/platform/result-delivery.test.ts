import { describe, expect, it } from "vitest";
import type { RunResult } from "@/lib/types/result";
import { confirmedContents, exportMarkdown, fenced } from "./result-delivery";

const result: RunResult = {
  runId: "one", title: "正文", status: "succeeded", contentStatus: "available",
  body: null, receipt: null, dataTime: null, createdAt: "2026-09-10T10:00:00Z", finishedAt: "2026-09-10T10:01:00Z", cancelRequestedAt: null,
  origin: { kind: "manual" }, sources: ["资料A"], missing: [], attachments: [], unknownEvidenceIds: [], freshness: [], errorCode: null,
};
describe("confirmed content selection", () => {
  it("keeps declared sections in order and does not duplicate legacy body/receipt", () => {
    const input = { ...result, body: "legacy duplicate", receipt: { duplicate: true }, sections: [
      { kind: "markdown" as const, label: "正文", value: "# hello", evidenceId: "node-ok" },
      { kind: "value" as const, label: "任意值", value: { text: "# not Markdown", reportId: false, collection: null } },
    ] };
    const options = confirmedContents(input);
    expect(options).toHaveLength(2);
    expect(options[1].format).toBe("json");
    const exported = exportMarkdown(input, options, {});
    expect(exported).toContain("# hello");
    expect(exported).toContain('"text": "# not Markdown"');
    expect(exported).not.toContain("node-ok");
    expect(exported).not.toContain("legacy duplicate");
  });
  it("supports historical body, receipt and generic output without business aliases", () => {
    const legacy = { ...result, body: "old content", receipt: { arbitrary: null } };
    expect(confirmedContents(legacy).map((v) => v.id)).toEqual(["body", "receipt"]);
    const generic = { ...result, sections: [{ kind: "value" as const, label: "工作流输出", value: { alien: [false, 0, null, ""] } }] };
    expect(exportMarkdown(generic, confirmedContents(generic), {})).toContain('"alien": [');
  });
  it.each(["partial", "unknown"] as const)("preserves %s, cancellation and provenance", (contentStatus) => {
    const input = { ...result, status: "cancelled" as const, contentStatus, body: "confirmed only", cancelRequestedAt: "2026-09-10T10:00:30Z", missing: ["missing data"] };
    const text = exportMarkdown(input, confirmedContents(input), {});
    expect(text).toContain(contentStatus === "unknown" ? "保存状态待核实" : "部分内容已确认");
    expect(text).toContain("取消请求时间");
    expect(text).toContain("已经确认的外部操作仍会保留");
    expect(text).toContain("missing data");
    expect(text).toContain("资料A");
    expect(text).toContain("数据时间：未提供");
  });
  it("exports read uncertainty without claiming an unconfirmed save", () => {
    const input = { ...result, body: "confirmed", contentStatus: "partial" as const, readUnknownEvidenceIds: ["read-op"] };
    const text = exportMarkdown(input, confirmedContents(input), {});
    expect(text).toContain("读取结果未确认");
    expect(text).not.toContain("read-op");
    expect(text).not.toContain("保存状态待核实");
  });
  it("requires explicit artifact loading and records excluded/deferred content", () => {
    const input = { ...result, body: "inline", deferredSections: ["长正文"], attachments: [{ kind: "artifact" as const, label: "产物", reference: { digest: `sha256:${"a".repeat(64)}`, mediaType: "application/json", sizeBytes: 999 } }] };
    const options = confirmedContents(input);
    expect(() => exportMarkdown(input, options, {})).toThrow(/尚未读取/);
    const partial = exportMarkdown(input, [options[0]], {});
    expect(partial).toContain("未纳入本文件的内容");
    expect(partial).toContain("保存在附件中的内容");
    expect(partial).not.toContain("sha256:");
    const full = exportMarkdown(input, options, { "artifact:0:0": '"# literal JSON"' });
    expect(full).toContain('```json\n"# literal JSON"\n```');
  });
  it("exports a large confirmed JSON value with many code delimiters without argument overflow", () => {
    const value = "`sample ".repeat(150000);
    const input = { ...result, sections: [{ kind: "value" as const, label: "Large confirmed value", value }] };
    expect(exportMarkdown(input, confirmedContents(input), {})).toContain(value);
  });
  it("has no pretend content for empty results and preserves fenced source bytes", () => {
    expect(() => exportMarkdown(result, [], {})).toThrow(/请先选择/);
    expect(fenced("```\nexact\n```", "json")).toBe("````json\n```\nexact\n```\n````");
  });
});


it("exports receipt confirmation without a service envelope while keeping declared body unchanged", () => {
  const input = { ...result, sections: [
    { kind: "receipt" as const, label: "保存确认", value: { operationId: "internal-operation", contentHash: "sha256:hidden" } },
    { kind: "markdown" as const, label: "原始正文", value: "User code: schema.operationId = 42;" },
  ] };
  const text = exportMarkdown(input, confirmedContents(input), {});
  expect(text).toContain("此项保存已确认。");
  expect(text).toContain("User code: schema.operationId = 42;");
  expect(text).not.toMatch(/internal-operation|sha256:hidden/);
});
