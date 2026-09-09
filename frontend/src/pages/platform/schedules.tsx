import { useState } from "react";
import { Link, useNavigate, useParams, useLocation } from "react-router";
import { ApiRequestError } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { useDisplayMode } from "@/hooks/use-display-mode";
import {
  availableTasks,
  taskDefaults,
  taskConstraintErrors,
} from "./task-catalog";
import { LaunchInputs } from "./launch-inputs";
import { ScheduleTiming, AppliedSchedulePreview } from "./schedule-timing";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import {
  FieldGroup,
  TextField,
  ChoiceField,
} from "@/components/shared/form-field";
import {
  usePlatformSchedule,
  usePackages,
  usePlatformMutations,
} from "@/hooks/use-workflow-platform";
import { initialParameters } from "@/lib/platform-authoring/parameter-values";
import { validateLaunchValueForSchema } from "@/lib/platform-authoring/schema/launch-input-state";
import type {
  Json,
  Schedule,
  ScheduleConfig,
} from "@/lib/types/workflow-platform";
import { ScheduleFireHistory } from "./schedule-fire-history";
import { RequestError } from "./feedback";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { ConfirmDeleteDialog } from "@/components/shared/confirm-delete-dialog";
export function SchedulePage() {
  const { scheduleId } = useParams();
  const query = usePlatformSchedule(scheduleId);
  if (scheduleId && query.isPending)
    return <InventoryStatePanel title="正在读取安排…" />;
  if (scheduleId && !query.data)
    return (
      <RequestError error={query.error} retry={() => void query.refetch()} />
    );
  return <ScheduleEditor key={scheduleId ?? "new"} schedule={query.data} />;
}
export interface ScheduleInput {
  packageKey: string;
  workflowKey: string;
  parameters: Json;
  name?: string;
}
function ScheduleEditor({ schedule }: { schedule?: Schedule }) {
  const { timeZone, expert } = useDisplayMode();
  const location = useLocation();
  const inherited = (location.state as { scheduleInput?: ScheduleInput } | null)
    ?.scheduleInput;
  const packages = usePackages();
  const mutations = usePlatformMutations();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<ScheduleConfig>(
    schedule ?? {
      creationId: crypto.randomUUID(),
      name:
        inherited?.name ??
        (inherited ? `${inherited.workflowKey} · 自动执行` : ""),
      packageKey: inherited?.packageKey ?? "",
      workflowKey: inherited?.workflowKey ?? "",
      parameters: inherited?.parameters ?? null,
      cron: "0 9 * * *",
      timeZone,
      overlapPolicy: "skip",
      catchupWindowSeconds: 60,
      paused: false,
    },
  );
  const [creationUncertain, setCreationUncertain] = useState(false);
  const [parametersDirty, setParametersDirty] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [acceptedTrigger, setAcceptedTrigger] = useState<string | null>(null);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [triggerId, setTriggerId] = useState(() => crypto.randomUUID());
  const pkg = packages.data?.items.find((p) => p.key === draft.packageKey);
  const workflow = pkg?.definition.workflows[draft.workflowKey];
  const set = <K extends keyof ScheduleConfig>(
    key: K,
    value: ScheduleConfig[K],
  ) => setDraft((d) => ({ ...d, [key]: value }));
  async function save() {
    try {
      if (parametersDirty) throw new Error("请先应用业务信息，再保存安排。");
      const value = draft.parameters;
      const businessErrors =
        workflow
          ? taskConstraintErrors(workflow.inputSchema, value)
          : {};
      if (Object.keys(businessErrors).length)
        throw new Error(Object.entries(businessErrors).map(([path, message]) => `${path}: ${message}`).join("; "));
      const issues = workflow
        ? validateLaunchValueForSchema(workflow.inputSchema, value)
        : [];
      if (issues.length)
        throw new Error(issues.map((i) => `${i.field}: ${i.issue}`).join("; "));
      if (!schedule) setCreationUncertain(true);
      const saved = await mutations.saveSchedule.mutateAsync({
        ...draft,
        parameters: value,
      });
      setError(null);
      setCreationUncertain(false);
      setDraft(saved);
      navigate(`/scheduled-tasks/${encodeURIComponent(saved.id)}`);
    } catch (e) {
      if (
        e instanceof ApiRequestError &&
        [400, 404, 422].includes(e.status) &&
        e.code !== "schedule_invalid"
      )
        setCreationUncertain(false);
      setError(e);
    }
  }
  async function trigger() {
    try {
      const accepted = await mutations.triggerSchedule.mutateAsync({
        id: schedule!.id,
        triggerId,
      });
      if (accepted.status !== "accepted")
        throw new Error("尚未确认执行请求，请使用同一请求重试。");
      setError(null);
      setAcceptedTrigger(accepted.triggerId);
      setTriggerId(crypto.randomUUID());
    } catch (e) {
      setError(e);
    }
  }
  return (
    <WorkspacePageShell
      contextBar={
        <PageContextBar
          title={schedule?.name ?? "安排重复执行"}
          description={
            draft.packageKey
              ? workflow?.name || draft.name
              : "选择任务，填写业务信息，再启用自动执行。"
          }
          actions={
            <div className="flex flex-wrap gap-2">
              <Button
                disabled={
                  parametersDirty ||
                  !draft.name ||
                  (!schedule && !workflow) ||
                  mutations.saveSchedule.isPending
                }
                onClick={() => void save()}
              >
                {schedule ? "保存安排" : "启用自动执行"}
              </Button>
              {schedule && (
                <Button
                  variant="outline"
                  disabled={
                    !workflow ||
                    schedule.desiredDeleted ||
                    mutations.triggerSchedule.isPending
                  }
                  onClick={() => void trigger()}
                >
                  立即执行
                </Button>
              )}
            </div>
          }
        />
      }
    >
      <FieldGroup>
        <RequestError error={error || packages.error} />
        {schedule && (
          <InventoryStatePanel
            title={
              <ResourceStatusBadge
                label={
                  schedule.desiredDeleted
                    ? `正在删除 · ${schedule.syncStatus}`
                    : schedule.syncStatus === "synced"
                      ? "安排已生效"
                      : schedule.syncStatus === "failed"
                        ? "安排未能生效"
                        : "正在应用安排"
                }
                tone={schedule.syncStatus === "failed" ? "danger" : "neutral"}
              />
            }
            description={
              schedule.syncErrorCode ??
              (schedule.syncStatus === "synced"
                ? `已生效版本 ${schedule.syncedRevision}`
                : `版本 ${schedule.revision} 尚未生效。`)
            }
          />
        )}
        {acceptedTrigger && (
          <InventoryStatePanel
            title="已接受执行请求"
            description={`请求 ${acceptedTrigger} 已进入执行队列，尚不代表任务完成。`}
            action={
              <Button asChild variant="outline">
                <Link to="/runs">查看结果</Link>
              </Button>
            }
          />
        )}
        {schedule && !workflow && (
          <InventoryStatePanel
            tone="warning"
            title="此任务已不可用"
            description="立即执行 is unavailable. Timing and pause settings can still be saved."
          />
        )}
        {creationUncertain && (
          <p role="alert">
            尚未确认新安排是否已生效。请使用原设置再次保存，或
            <Link
              className="underline"
              to={`/scheduled-tasks/${draft.creationId}`}
            >
              查看此安排的状态
            </Link>
            ；系统会沿用同一请求，避免创建重复安排。
          </p>
        )}
        <fieldset disabled={creationUncertain} className="min-w-0">
          <FieldGroup>
            <TextField
              label="安排名称"
              value={draft.name}
              onChange={(v) => set("name", v)}
            />
            {!expert && !schedule && !inherited && (
              <ChoiceField
                label="选择任务"
                value={
                  draft.packageKey && draft.workflowKey
                    ? `${draft.packageKey}/${draft.workflowKey}`
                    : ""
                }
                options={availableTasks(packages.data?.items ?? []).map(
                  (task) => ({
                    value: `${task.packageKey}/${task.workflowKey}`,
                    label: task.title,
                  }),
                )}
                onChange={(value) => {
                  const task = availableTasks(packages.data?.items ?? []).find(
                    (item) =>
                      `${item.packageKey}/${item.workflowKey}` === value,
                  );
                  if (task) {
                    setDraft((current) => ({
                      ...current,
                      packageKey: task.packageKey,
                      workflowKey: task.workflowKey,
                      name: current.name || `${task.title} · 自动执行`,
                      parameters: taskDefaults(task.workflow.inputSchema),
                    }));
                    setParametersDirty(false);
                  }
                }}
              />
            )}
            <div hidden={!expert}>
              <div className="flex flex-col gap-4">
                <ChoiceField
                  label="任务包"
                  value={draft.packageKey}
                  disabled={!!schedule}
                  options={(packages.data?.items ?? []).map((p) => ({
                    value: p.key,
                    label: p.name,
                  }))}
                  onChange={(v) => {
                    setDraft((d) => ({ ...d, packageKey: v, workflowKey: "" }));
                    set("parameters", {});
                    setParametersDirty(false);
                  }}
                />
                <ChoiceField
                  label="任务"
                  value={draft.workflowKey}
                  disabled={!!schedule}
                  options={Object.entries(pkg?.definition.workflows ?? {}).map(
                    ([value, w]) => ({ value, label: w.name || value }),
                  )}
                  onChange={(v) => {
                    const selected = pkg?.definition.workflows[v];
                    setDraft((current) => ({
                      ...current,
                      workflowKey: v,
                      name: current.name || `${selected?.name || v} · 自动执行`,
                      parameters: selected
                        ? initialParameters(selected.inputSchema)
                        : null,
                    }));
                    setParametersDirty(false);
                  }}
                />
              </div>
            </div>
            <ScheduleTiming draft={draft} onChange={setDraft} />
            <p className="text-sm">
              上一次尚未结束时：{" "}
              {draft.overlapPolicy === "skip"
                ? "跳过本次执行"
                : draft.overlapPolicy === "buffer_one"
                  ? "保留一次等待执行"
                  : "允许同时执行"}
              。错过执行超过 {draft.catchupWindowSeconds} 秒不再补跑。
            </p>
            <details open={expert}>
              <summary className="cursor-pointer text-sm">高级执行设置</summary>
              <div className="mt-3 flex flex-col gap-4">
                <ChoiceField
                  label="上一次尚未结束时"
                  value={draft.overlapPolicy}
                  options={[
                    { value: "skip", label: "跳过本次执行" },
                    {
                      value: "buffer_one",
                      label: "保留一次，等待上次结束",
                    },
                    { value: "allow", label: "允许同时执行" },
                  ]}
                  onChange={(v) =>
                    set("overlapPolicy", v as ScheduleConfig["overlapPolicy"])
                  }
                />
                <TextField
                  label="错过执行的补跑期限（秒；超过期限不再补跑）"
                  type="number"
                  value={String(draft.catchupWindowSeconds)}
                  onChange={(v) => set("catchupWindowSeconds", Number(v))}
                />
              </div>
            </details>
            <ChoiceField
              label="自动执行状态"
              value={draft.paused ? "paused" : "active"}
              options={[
                { value: "active", label: "已启用" },
                { value: "paused", label: "已暂停" },
              ]}
              onChange={(v) => set("paused", v === "paused")}
            />
            <p className="text-sm text-muted-foreground">
              暂停只停止未来自动执行，不会取消当前任务。每次执行使用当时已保存的任务和连接，已有结果保持不变。
            </p>
            {workflow && (
              <>
                <div>
                  <LaunchInputs
                    technical={expert}
                    key={`${draft.packageKey}/${draft.workflowKey}`}
                    schema={workflow.inputSchema}
                    inputHints={workflow.presentation?.inputHints}
                    value={draft.parameters}
                    onChange={(value) => set("parameters", value)}
                    onDirtyChange={setParametersDirty}
                  />
                </div>
                {parametersDirty && !expert && (
                  <p role="alert">
                    专家输入尚未应用，请先应用或放弃修改，避免覆盖草稿。
                  </p>
                )}
              </>
            )}
          </FieldGroup>
        </fieldset>
        {schedule && (
          <>
            <AppliedSchedulePreview
              id={schedule.id}
              revision={schedule.revision}
            />
            <ScheduleFireHistory scheduleId={schedule.id} />
            <p className="text-sm text-muted-foreground">
              每次执行均有独立记录，已有结果继续保留本次安排来源。
            </p>
            <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
              删除安排
            </Button>
            <ConfirmDeleteDialog
              open={deleteOpen}
              onOpenChange={setDeleteOpen}
              title="删除这个安排？"
              description="停止未来执行，已有结果及其安排来源会保留。"
              isPending={mutations.deleteSchedule.isPending}
              onConfirm={() =>
                mutations.deleteSchedule
                  .mutateAsync(schedule.id)
                  .then(() => navigate("/scheduled-tasks"))
                  .catch(setError)
              }
            />
          </>
        )}
      </FieldGroup>
    </WorkspacePageShell>
  );
}
