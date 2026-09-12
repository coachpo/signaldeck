import { useEffect, useRef, useState } from "react";
import type { PackageDefinition } from "@/lib/types/workflow-platform";
import { FieldGroup, TextField } from "@/components/shared/form-field";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { ConfirmDeleteDialog } from "@/components/shared/confirm-delete-dialog";
import { Button } from "@/components/ui/button";
import { parseDefinition, updateSource } from "@/lib/platform-authoring/package-source";
import { agentLabel, freshKey, newAgent, newWorkflow, stepLabels, stepRemovalBlockers, workflowLabel } from "@/lib/platform-authoring/package-authoring";
import { AgentProperties } from "./package-agent-properties";
import { NodeProperties, WorkflowProperties } from "./package-properties";
import type { AuthoringCatalog } from "./package-controls";

const emptyCatalog: AuthoringCatalog = { models: [], connections: [], tools: [] };

export function PackageStructure({ source, onChange, catalog = emptyCatalog, selected: controlledSelection, onSelect }: {
  source: string; onChange: (source: string) => void; catalog?: AuthoringCatalog;
  selected?: string[]; onSelect?: (selection: string[]) => void;
}) {
  const [localSelection, setLocalSelection] = useState<string[]>([]);
  const [removal, setRemoval] = useState<{ path: string[]; label: string } | null>(null);
  const [notice, setNotice] = useState("");
  const selected = controlledSelection ?? localSelection;
  const propertyPanel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (selected.length) {
      propertyPanel.current?.focus({ preventScroll: true });
      propertyPanel.current?.scrollIntoView?.({ block: "start", behavior: "instant" });
    }
  }, [selected]);
  const select = (path: string[]) => { setLocalSelection(path); onSelect?.(path); setNotice(""); };
  let definition: PackageDefinition;
  try { definition = parseDefinition(source); } catch {
    return <InventoryStatePanel tone="warning" title="无法读取这份工作流" description="请重新导入有效的工作流文件。当前内容已保留，导出后也可交给提供者检查。" />;
  }
  const edit = (path: string[], value: unknown) => onChange(updateSource(source, path, value));
  const selectedWorkflow = selected[0] === "workflows" ? definition.workflows[selected[1]] : undefined;
  function remove() {
    if (!selected.length) return;
    if (selected[0] === "agents") {
      const usedBy = Object.entries(definition.workflows).filter(([, workflow]) => Object.values(workflow.nodes).some((node) => node.uses === selected[1])).map(([key]) => workflowLabel(definition, key));
      if (usedBy.length) { setNotice(`仍有任务流程使用此助手：${usedBy.join("、")}。请先为相关步骤选择其他助手。`); return; }
      if (Object.keys(definition.agents).length === 1) { setNotice("请至少保留一位助手。可以修改这位助手，或先添加其他助手。"); return; }
      setRemoval({ path: selected, label: agentLabel(definition, selected[1]) });
    } else if (selected.length === 2) {
      if (Object.keys(definition.workflows).length === 1) { setNotice("请至少保留一个任务流程。可以修改当前流程，或先添加其他流程。"); return; }
      setRemoval({ path: selected, label: workflowLabel(definition, selected[1]) });
    } else if (selectedWorkflow) {
      if (Object.keys(selectedWorkflow.nodes).length === 1) { setNotice("任务流程至少需要一个步骤。请先添加其他步骤。"); return; }
      const labels = stepLabels(definition, selected[1]);
      const blockers = stepRemovalBlockers(selectedWorkflow, selected[3], labels);
      if (blockers.length) { setNotice(`以下内容仍在使用此步骤：${blockers.join("、")}。请先调整它们的信息来源或执行顺序。`); return; }
      setRemoval({ path: selected, label: labels[selected[3]] });
    }
  }
  return <FieldGroup>
    <div className="grid gap-3 md:grid-cols-2"><TextField label="工作流集名称" value={definition.metadata.name} onChange={(v) => edit(["metadata", "name"], v)} /><TextField label="用途说明" value={definition.metadata.description ?? ""} onChange={(v) => edit(["metadata", "description"], v)} /></div>
    <div className="grid min-w-0 gap-4 lg:grid-cols-[15rem_minmax(0,1fr)]">
      <nav aria-label="制作内容" className="flex flex-col gap-4 self-start lg:sticky lg:top-0">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold">任务流程</h2>
          {Object.entries(definition.workflows).map(([key, workflow]) => <div key={key} className="flex flex-col gap-1">
            <Button className="justify-start whitespace-normal text-left" variant={selected.join(".") === `workflows.${key}` ? "secondary" : "ghost"} onClick={() => select(["workflows", key])}>{workflowLabel(definition, key)}</Button>
            {Object.keys(workflow.nodes ?? {}).map((node) => <Button className="justify-start whitespace-normal pl-5 text-left text-xs" key={node} variant={selected.join(".") === `workflows.${key}.nodes.${node}` ? "secondary" : "ghost"} onClick={() => select(["workflows", key, "nodes", node])}>{stepLabels(definition, key)[node]}</Button>)}
            <Button size="sm" variant="outline" aria-label={`为${workflowLabel(definition, key)}添加步骤`} onClick={() => {
              const nodeKey = freshKey("step");
              const agentKey = Object.keys(definition.agents)[0];
              edit(["workflows", key, "nodes", nodeKey], { uses: agentKey, inputMapping: { ref: "workflow.input" } });
              select(["workflows", key, "nodes", nodeKey]);
            }}>添加步骤</Button>
          </div>)}
          <Button variant="outline" onClick={() => {
            const key = freshKey("task"), agentKey = Object.keys(definition.agents)[0];
            edit(["workflows", key], newWorkflow(Object.keys(definition.workflows).length + 1, agentKey, definition.agents[agentKey]));
            select(["workflows", key]);
          }}>添加任务流程</Button>
        </div>
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold">可复用助手</h2>
          {Object.keys(definition.agents).map((key) => <Button className="justify-start whitespace-normal text-left" key={key} variant={selected.join(".") === `agents.${key}` ? "secondary" : "ghost"} onClick={() => select(["agents", key])}>{agentLabel(definition, key)}</Button>)}
          <Button variant="outline" onClick={() => {
            const key = freshKey("assistant");
            edit(["agents", key], newAgent(Object.keys(definition.agents).length + 1, catalog.models[0]?.value));
            select(["agents", key]);
          }}>添加助手</Button>
        </div>
      </nav>
      <div ref={propertyPanel} tabIndex={-1} role="region" aria-label="所选制作内容" className="flex min-w-0 flex-col gap-4">
        {notice && <InventoryStatePanel tone="warning" title="暂时无法移除" description={notice} />}
        {!selected.length && <InventoryStatePanel title="开始制作任务" description="先选择一个任务流程，设置开始时需要填写的信息；再选择助手，说明它要做什么，并安排每个步骤。" action={<Button onClick={() => select(["workflows", Object.keys(definition.workflows)[0]])}>设置第一个任务流程</Button>} />}
        {selected[0] === "agents" && definition.agents[selected[1]] && <AgentProperties key={selected.join(".")} agent={definition.agents[selected[1]]} catalog={catalog} edit={(path, value) => edit([...selected, ...path], value)} />}
        {selectedWorkflow && selected.length === 2 && <WorkflowProperties key={selected.join(".")} workflow={selectedWorkflow} definition={definition} workflowKey={selected[1]} catalog={catalog} edit={(path, value) => edit([...selected, ...path], value)} />}
        {selectedWorkflow && selected.length === 4 && selectedWorkflow.nodes[selected[3]] && <NodeProperties key={selected.join(".")} node={selectedWorkflow.nodes[selected[3]]} nodeKey={selected[3]} definition={definition} workflowKey={selected[1]} catalog={catalog} edit={(path, value) => edit([...selected, ...path], value)} />}
        {selected.length > 0 && <Button variant="outline" className="self-start text-destructive" onClick={remove}>移除{selected[0] === "agents" ? "助手" : selected.length === 2 ? "任务流程" : "步骤"}</Button>}
      </div>
    </div>
    <ConfirmDeleteDialog open={!!removal} title={`移除${removal?.label ?? "所选内容"}？`} description="保存工作流后，此内容将不再用于新的任务。已经运行过的任务和结果会保留。" confirmLabel="确认移除" onOpenChange={(open) => { if (!open) setRemoval(null); }} onConfirm={() => {
      if (!removal) return;
      edit(removal.path, undefined); select([]); setRemoval(null);
    }} />
  </FieldGroup>;
}
