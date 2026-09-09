import {TaskRecent} from "./task-recent";
import { useState } from "react";
import { Link } from "react-router";
import { useDisplayMode } from "@/hooks/use-display-mode";
import { usePackages } from "@/hooks/use-workflow-platform";
import { useTaskMutations, useTaskPresets } from "@/hooks/use-task-experience";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/shared/form-field";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { RequestError } from "./feedback";
import { availableTasks } from "./task-catalog";
import type { TaskPreset } from "@/lib/types/task-experience";
export function TasksPage() {
  const { expert } = useDisplayMode();
  const packages = usePackages();
  const presets = useTaskPresets();
  const { deletePreset, savePreset } = useTaskMutations();
  const [error, setError] = useState<unknown>(null);
  const [search, setSearch] = useState("");
  const tasks = availableTasks(packages.data?.items ?? []);
  const saved = [...(presets.data?.items ?? [])].sort(
    (a, b) =>
      Number(b.isPinned) - Number(a.isPinned) ||
      Number(b.isFavorite) - Number(a.isFavorite) ||
      a.name.localeCompare(b.name),
  );
  async function remove(id: string) {
    try {
      await deletePreset.mutateAsync(id);
    } catch (e) {
      setError(e);
    }
  }
  async function toggle(preset: TaskPreset, field: "isPinned" | "isFavorite") {
    try {
      await savePreset.mutateAsync({ ...preset, [field]: !preset[field] });
    } catch (e) {
      setError(e);
    }
  }
  return (
    <WorkspacePageShell
      contextBar={
        <PageContextBar
          title="任务"
          description="选择要做的事，填写业务信息后开始。"
          actions={
            <Button variant="outline" asChild>
              <Link to="/scheduled-tasks">自动执行</Link>
            </Button>
          }
        />
      }
    >
      <div className="flex flex-col gap-5">
        <RequestError error={error} />
        <TextField
          label="搜索任务或常用配置"
          value={search}
          onChange={setSearch}
        />
        {packages.isPending ? (
          <InventoryStatePanel title="正在读取任务…" />
        ) : packages.error ? (
          <RequestError
            error={packages.error}
            retry={() => void packages.refetch()}
          />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {tasks
              .filter((t) => `${t.title} ${t.description}`.includes(search))
              .map((task) => (
                <section
                  key={`${task.packageKey}/${task.workflowKey}`}
                  className="flex flex-col items-start gap-3 rounded-md border border-ui-separator bg-ui-surface p-4"
                >
                  <h2 className="font-medium">{task.title}</h2>
                  <p className="text-sm text-muted-foreground">
                    {task.description}
                  </p>
                  <p className="text-sm">
                    {task.supported
                      ? "选择后核对所需连接和保存位置。"
                      : "此任务通过完整 JSON 编辑输入。"}
                  </p>
                  <TaskRecent
                    packageKey={task.packageKey}
                    workflowKey={task.workflowKey}
                  />
                  <Button asChild>
                    <Link
                      to={`/tasks/new?packageKey=${encodeURIComponent(task.packageKey)}&workflowKey=${encodeURIComponent(task.workflowKey)}`}
                    >
                      选择任务
                    </Link>
                  </Button>
                </section>
              ))}
          </div>
        )}
        {search &&
          !tasks.some((t) => `${t.title} ${t.description}`.includes(search)) &&
          !saved.some((p) => p.name.includes(search)) && (
            <InventoryStatePanel
              title="没有匹配的任务或配置"
              description="试试其他关键词，或清空搜索。"
            />
          )}
        {!packages.isPending && !tasks.length && (
          <InventoryStatePanel
            title="暂无普通任务"
            description="先在专家工作区导入首批任务定义。"
          />
        )}
        <section className="flex flex-col gap-3">
          <h2 className="font-medium">常用配置与收藏</h2>
          <RequestError
            error={presets.error}
            retry={() => void presets.refetch()}
          />
          {saved
            .filter((p) => p.name.includes(search))
            .map((p) => (
              <div
                key={p.id}
                className="flex flex-wrap items-center gap-3 rounded-md border border-ui-separator p-3"
              >
                <div className="min-w-0 flex-1">
                  <Link
                    className="font-medium underline underline-offset-4"
                    to={`/tasks/new?presetId=${encodeURIComponent(p.id)}`}
                  >
                    {p.name}
                  </Link>
                  {p.needsRevalidation && (
                    <p className="text-sm text-muted-foreground">
                      定义已更新，使用前重新核对输入。
                    </p>
                  )}
                </div>
                <Button
                  variant="ghost"
                  onClick={() => void toggle(p, "isFavorite")}
                >
                  {p.isFavorite ? "取消收藏" : "收藏"}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => void toggle(p, "isPinned")}
                >
                  {p.isPinned ? "取消置顶" : "置顶"}
                </Button>
                <Button variant="ghost" onClick={() => void remove(p.id)}>
                  删除配置
                </Button>
              </div>
            ))}
          {!saved.length && !presets.isPending && (
            <p className="text-sm text-muted-foreground">
              填写任务后，可以选择保存常用输入。无需先保存即可执行。
            </p>
          )}
        </section>
        {expert && (
          <Button variant="outline" className="self-start" asChild>
            <Link to="/workflow-packages">全部任务定义与专家制作</Link>
          </Button>
        )}
      </div>
    </WorkspacePageShell>
  );
}
export { TaskPage } from "./task-launch";
