import { useDisplayMode } from "@/hooks/use-display-mode";
import { Link } from "react-router";
import { MarkdownContent } from "@/components/shared/markdown-content";
import type { ResultSection } from "@/lib/types/result";
import { ResultValue } from "./result-content";
import { safePluginPageUrl } from "./plugin-links";
import { runSearch } from "./result-navigation";

export function DeclaredResultSections({ sections, search }: {
  sections: ResultSection[];
  search: URLSearchParams;
}) {
  const { expert } = useDisplayMode();
  return sections.map((section, index) => {
    const href = safePluginPageUrl(section.href);
    return (
      <section key={index} className="rounded border border-border bg-card p-4" aria-label={section.label}>
        {section.kind === "receipt" ? (
          <details open={expert}>
            <summary className="cursor-pointer font-semibold">{section.label}（完整原值）</summary>
            <ResultValue value={section.value} />
          </details>
        ) : <>
        <h2 className="mb-3 font-semibold">{section.label}</h2>
        {section.kind === "markdown" && typeof section.value === "string" ? (
          <MarkdownContent>{section.value}</MarkdownContent>
        ) : section.kind === "link" && href ? (
          <a href={href} target="_blank" rel="noreferrer" className="mr-3 underline">{section.label}</a>
        ) : <ResultValue value={section.value} />}
        </>}
        {section.severity && (
          <p className="text-sm text-muted-foreground">
            {section.severity === "missing" ? "资料缺失" : section.severity === "warning" ? "注意" : "告知"}
          </p>
        )}
        {section.evidenceId && (
          <Link className="text-sm underline" to={`?${runSearch(search, { tab: "evidence", target: section.evidenceId })}`}>
            查看此项证据
          </Link>
        )}
      </section>
    );
  });
}
