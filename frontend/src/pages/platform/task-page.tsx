import { useState } from "react";
import { Link, useLocation, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { useTaskDraft } from "@/hooks/use-task-drafts";
import { usePackages } from "@/hooks/use-workflow-platform";
import { useTaskPresets, useTaskReuse } from "@/hooks/use-task-experience";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { RequestError } from "./feedback";
import { taskDefaults } from "./task-catalog";
import { TaskForm } from "./task-launch";

export function TaskPage() {
  const location = useLocation();
  const [params] = useSearchParams();
  const [initialLaunchId] = useState(() => crypto.randomUUID());
  const draftId = params.get("draftId") ?? undefined;
  const storedDraft = useTaskDraft(draftId);
  const restored = storedDraft.data;
  const packages = usePackages();
  const presets = useTaskPresets();
  const fromRun = params.get("fromRun") ?? undefined;
  const reuse = useTaskReuse(fromRun);
  const presetId = params.get("presetId");
  const preset = presets.data?.items.find((p) => p.id === presetId);
  const historical = reuse.data;
  const packageKey =
    restored?.packageKey ??
    historical?.packageKey ??
    preset?.packageKey ??
    params.get("packageKey") ??
    "";
  const workflowKey =
    restored?.workflowKey ??
    historical?.workflowKey ??
    preset?.workflowKey ??
    params.get("workflowKey") ??
    "";
  const pkg = packages.data?.items.find((p) => p.key === packageKey);
  const workflow = pkg?.definition.workflows[workflowKey];
  if (
    (draftId && storedDraft.isPending) ||
    packages.isPending ||
    (fromRun && reuse.isPending) ||
    (presetId && presets.isPending)
  )
    return <InventoryStatePanel title="正在读取任务…" />;
  if (storedDraft.error || packages.error || reuse.error || (presetId && presets.error))
    return (
      <RequestError error={storedDraft.error ?? packages.error ?? reuse.error ?? presets.error} retry={() => {
        if (storedDraft.error) void storedDraft.refetch();
        if (packages.error) void packages.refetch();
        if (reuse.error) void reuse.refetch();
        if (presets.error) void presets.refetch();
      }} />
    );
  if ((!restored && !historical && (!pkg || !workflow)) || (presetId && !preset))
    return (
      <InventoryStatePanel
        title="无法找到任务"
        description="任务或常用配置可能已删除。可以返回首页选择其他任务。"
        action={<Button asChild><Link to="/">返回任务首页</Link></Button>}
      />
    );
  const schema = restored?.workflow.inputSchema ?? historical?.inputSchema ?? workflow!.inputSchema;
  const context = `${packageKey}/${workflowKey}`;
  const formKey = location.state?.taskFormContext === context && typeof location.state?.taskFormKey === "string"
    ? location.state.taskFormKey as string
    : `${context}/${restored?.launchId ?? initialLaunchId}`;
  return (
    <TaskForm
      key={formKey}
      formKey={formKey}
      initialLaunchId={initialLaunchId}
      packageKey={packageKey}
      workflowKey={workflowKey}
      packageHash={restored?.packageHash ?? historical?.packageHash ?? pkg!.packageHash}
      schema={schema}
      workflow={restored?.workflow ?? historical?.workflow ?? workflow}
      restored={restored}
      initial={
        restored ? restored.parameters : historical ? historical.parameters : preset?.hasParameters ? preset.parameters : taskDefaults(schema)
      }
      historical={historical}
      preset={preset}
    />
  );
}
