import { Link } from "react-router";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ResultSection } from "@/lib/types/result";
import { ResultValue } from "./result-content";
import { safePluginPageUrl } from "./plugin-links";
import { runSearch } from "./result-navigation";

export function DeclaredResultSections({ sections, search }: {
  sections: ResultSection[];
  search: URLSearchParams;
}) {
  return sections.map((section, index) => {
    const href = safePluginPageUrl(section.href);
    return (
      <section key={index} className="rounded border border-border bg-card p-4" aria-label={section.label}>
        <h2 className="mb-3 font-semibold">{section.label}</h2>
        {section.kind === "markdown" && typeof section.value === "string" ? (
          <Markdown remarkPlugins={[remarkGfm]}>{section.value}</Markdown>
        ) : section.kind === "link" && href ? (
          <a href={href} target="_blank" rel="noreferrer" className="underline">{section.label}</a>
        ) : <ResultValue value={section.value} />}
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
