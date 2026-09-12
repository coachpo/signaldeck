import { Link, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import type { ExecutionEvidence, Json, JsonObject, RunDetail } from "@/lib/types/workflow-platform";
import { ResultValue } from "./result-content";
import { evidenceName } from "./result-context";
import { runSearch } from "./result-navigation";
import { resultStatusLabels, resultStatusTone } from "./result-labels";

/** This component accepts business values; execution metadata is never passed here. */
export function ArtifactValue({ value, label, schema }: { value: Json; label: string; schema?: JsonObject }) {
  return <section aria-label={label} className="flex min-w-0 flex-col gap-3">
    <h3 className="font-medium">{label}</h3>
    <ResultValue value={value} schema={schema} />
  </section>;
}

export function EvidenceTree({ evidence, selected, run }: {
  evidence: ExecutionEvidence[]; selected?: string | null; run?: RunDetail;
}) {
  const [search] = useSearchParams();
  const ids = new Set(evidence.map((item) => item.id));
  const roots = evidence.filter((item) => !item.parentId || !ids.has(item.parentId));
  const childrenByParent = new Map<string, ExecutionEvidence[]>();
  for (const item of evidence) {
    if (!item.parentId) continue;
    const siblings = childrenByParent.get(item.parentId) ?? [];
    siblings.push(item);
    childrenByParent.set(item.parentId, siblings);
  }
  function rows(items: ExecutionEvidence[], ancestors: Set<string>) {
    return <ul className="flex flex-col gap-2">
      {items.filter((item) => !ancestors.has(item.id)).map((item) => {
        const children = childrenByParent.get(item.id) ?? [];
        return <li key={item.id} className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <Button asChild variant={selected === item.id ? "secondary" : "outline"}>
              <Link to={`?${runSearch(search, { tab: "evidence", target: item.id })}`}>
                {evidenceName(item, run)} · 第 {item.attempt} 次
              </Link>
            </Button>
            <ResourceStatusBadge label={item.status === "unknown" ? "结果未确认" : resultStatusLabels[item.status] ?? "等待开始"} tone={resultStatusTone(item.status)} />
          </div>
          {children.length > 0 && <div className="ml-4 border-l border-ui-separator pl-3">{rows(children, new Set([...ancestors, item.id]))}</div>}
        </li>;
      })}
    </ul>;
  }
  return <div aria-label="步骤与服务操作">{roots.length ? rows(roots, new Set()) : <p>尚未开始处理。开始后，这里会自动显示各步骤进度。</p>}</div>;
}
