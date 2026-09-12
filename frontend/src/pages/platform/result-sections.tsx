import { Link } from "react-router";
import { MarkdownContent } from "@/components/shared/markdown-content";
import type { ResultSection } from "@/lib/types/result";
import { ResultValue } from "./result-content";
import { safePluginPageUrl } from "./plugin-links";
import { runSearch } from "./result-navigation";
import { sectionSchema } from "./result-context";
import type { RunDetail } from "@/lib/types/workflow-platform";
import { groupResultSections, type SectionSource } from "./result-section-groups";

export function DeclaredResultSections({ sections, search, run }: {
  sections: ResultSection[];
  search: URLSearchParams;
  run?: RunDetail;
}) {
  return groupResultSections(sections, run).map(({ section, index, sources }) => {
    const href = safePluginPageUrl(section.href);
    return (
      <section key={index} className="rounded border border-border bg-card p-4" aria-label={section.label}>
        {section.kind === "receipt" ? (
          <><h2 className="mb-3 font-semibold">{section.label}</h2><p>此项保存已确认。</p></>
        ) : <>
        <h2 className="mb-3 font-semibold">{section.label}</h2>
        {section.kind === "markdown" && typeof section.value === "string" ? (
          <MarkdownContent>{section.value}</MarkdownContent>
        ) : section.kind === "link" && href ? (
          <a href={href} target="_blank" rel="noreferrer" className="mr-3 underline">{section.label}</a>
        ) : section.kind === "link" ? <p>保存位置暂时无法打开，请查看执行过程。</p> : <ResultValue value={section.value} schema={sectionSchema(run, section)} />}
        </>}
        {section.severity && (
          <p className="text-sm text-muted-foreground">
            {section.severity === "missing" ? "资料缺失" : section.severity === "warning" ? "注意" : "告知"}
          </p>
        )}
        {sources.length > 1 ? <ResultSectionSources sources={sources} runId={run?.id} search={search} /> : section.evidenceId && (
          <Link className="text-sm underline" to={`?${runSearch(search, { tab: "evidence", target: section.evidenceId })}`}>
            查看相关步骤
          </Link>
        )}
      </section>
    );
  });
}

export function ResultSectionSources({ sources, runId, search }: { sources: SectionSource[]; runId?: string; search: URLSearchParams }) {
  return <div className="mt-3 flex flex-col gap-2 text-sm" aria-label="内容来源">
    <p className="font-medium">内容来源</p>
    {sources.map((source) => source.evidenceId ? <Link key={source.index} className="underline" to={`${runId ? `/runs/${encodeURIComponent(runId)}` : ""}?${runSearch(search, { tab: "evidence", target: source.evidenceId })}`}>查看{source.label}</Link> : <p key={source.index} className="text-muted-foreground">{source.label}</p>)}
  </div>;
}
