import { Link, useSearchParams } from "react-router";
import type { ExecutionEvidence, RunDetail } from "@/lib/types/workflow-platform";
import type { ResultSection } from "@/lib/types/result";
import { Button } from "@/components/ui/button";
import { mappingReferences, runSources, runWorkflow, stepName } from "./result-context";
import { RecordedMapping } from "./result-rules";
import { runSearch } from "./result-navigation";
import { resultStatusLabels } from "./result-labels";

export function ResultInputSources({ run, item, sections = [] }: {
  run: RunDetail; item: ExecutionEvidence; sections?: ResultSection[];
}) {
  const [search] = useSearchParams();
  const workflow = runWorkflow(run);
  const node = workflow?.nodes[item.nodeId];
  if (!node) return null;
  const references = mappingReferences(node.inputMapping);
  const inputs = references.some((reference) => reference === "workflow.input" || reference.startsWith("workflow.input."));
  const upstream = run.spec.plan.nodeOrder.filter((id) => references.some((reference) => reference === `nodes.${id}.output` || reference.startsWith(`nodes.${id}.output.`)));
  return <section className="flex min-w-0 flex-col gap-3 text-sm" aria-label="步骤的信息来源">
    <h3 className="font-medium">{item.kind === "node" || item.kind === "agent" ? "本步骤的信息来源" : "所属步骤的信息来源"}</h3>
    <RecordedMapping value={node.inputMapping} targetSchema={run.spec.definition.agents[node.uses]?.inputSchema} sources={runSources(run, item.nodeId)} />
    {inputs && <Button asChild variant="outline"><Link to={`?${runSearch(search, { tab: "snapshot" })}`}>查看本次填写的信息</Link></Button>}
    {upstream.length > 0 && <ul className="flex flex-col gap-3">{upstream.map((id) => {
      const latest = run.evidence.filter((entry) => entry.nodeId === id && entry.kind === "node").sort((left, right) => right.attempt - left.attempt)[0];
      const readable = sections.some((section) => section.nodeId === id);
      return <li key={id} className="flex flex-col gap-2">
        <p>{stepName(run, id)}：{latest?.status === "unknown" ? "结果未确认" : latest ? resultStatusLabels[latest.status] ?? "等待开始" : "尚未开始"}</p>
        {!readable && latest?.status === "succeeded" && <p className="text-muted-foreground">这个步骤没有单独提供可读正文；可以检查其执行进度，或在结果页阅读已确认内容。</p>}
        <Button asChild variant="outline"><Link to={`?${runSearch(search, latest ? { tab: "evidence", target: latest.id } : { tab: "evidence", node: id })}`}>{readable ? `查看${stepName(run, id)}的已确认内容` : `查看${stepName(run, id)}的执行进度`}</Link></Button>
      </li>;
    })}</ul>}
  </section>;
}
