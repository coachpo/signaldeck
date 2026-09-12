import { useEffect, useState } from "react";
import { useUnsavedWork } from "@/hooks/use-unsaved-work";
import { scheduleDrafts, scheduleTriggerDrafts, scheduleConfigKey } from "./schedule-drafts";
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
  const { timeZone } = useDisplayMode();
  const location = useLocation();
  const inherited = (location.state as { scheduleInput?: ScheduleInput } | null)
    ?.scheduleInput;
  const packages = usePackages();
  const mutations = usePlatformMutations();
  const navigate = useNavigate();
  const draftKey = schedule?.id ?? `new:${JSON.stringify(inherited ?? null)}`;
  const restored = scheduleDrafts.get(draftKey);
  const [draft, setDraft] = useState<ScheduleConfig>(
    restored?.value ?? schedule ?? {
      creationId: crypto.randomUUID(),
      name:
        inherited?.name ??
        (inherited ? "任务自动执行" : ""),
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
  const [creationUncertain, setCreationUncertain] = useState(restored?.creationUncertain ?? false);
  const [savedValue, setSavedValue] = useState(restored?.savedValue ?? scheduleConfigKey(draft));
  const [validationMessage, setValidationMessage] = useState("");
  const [savedNotice, setSavedNotice] = useState("");
  const [parametersDirty, setParametersDirty] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [acceptedTrigger, setAcceptedTrigger] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [triggerId, setTriggerId] = useState(() => restored?.triggerId ?? scheduleTriggerDrafts.get(schedule?.id ?? "") ?? crypto.randomUUID());
  const [triggerUncertain, setTriggerUncertain] = useState(restored?.triggerUncertain ?? scheduleTriggerDrafts.has(schedule?.id ?? ""));
  const changed = scheduleConfigKey(draft) !== savedValue;
  const unsaved = changed || parametersDirty || creationUncertain || triggerUncertain;
  useUnsavedWork(unsaved);
  useEffect(() => {
    if (unsaved) scheduleDrafts.set(draftKey, { value: draft, savedValue, creationUncertain, triggerId, triggerUncertain });
    else scheduleDrafts.delete(draftKey);
  }, [draftKey, draft, savedValue, creationUncertain, triggerId, triggerUncertain, unsaved]);
  const pkg = packages.data?.items.find((p) => p.key === draft.packageKey);
  const workflow = pkg?.definition.workflows[draft.workflowKey];
  const set = <K extends keyof ScheduleConfig>(
    key: K,
    value: ScheduleConfig[K],
  ) => setDraft((d) => ({ ...d, [key]: value }));
  async function save() {
    try {
      setValidationMessage("");
      if (parametersDirty) { setValidationMessage("请先完成业务信息，再保存安排。"); return; }
      if (draft.catchupWindowSeconds < 10 || !Number.isInteger(draft.catchupWindowSeconds)) { setValidationMessage("补做期限至少为 10 秒，请调整后保存。"); return; }
      const value = draft.parameters;
      const businessErrors =
        workflow
          ? taskConstraintErrors(workflow.inputSchema, value)
          : {};
      if (Object.keys(businessErrors).length) { setValidationMessage(Object.values(businessErrors).join("；")); return; }
      const issues = workflow
        ? validateLaunchValueForSchema(workflow.inputSchema, value)
        : [];
      if (issues.length) { setValidationMessage("请检查业务信息中标出的内容，补齐或修正后再保存。"); return; }
      if (!schedule) setCreationUncertain(true);
      const saved = await mutations.saveSchedule.mutateAsync({
        ...draft,
        parameters: value,
      });
      setError(null);
      setCreationUncertain(false);
      setDraft(saved);
      setSavedValue(scheduleConfigKey(saved));
      setSavedNotice("安排已保存，请查看下方状态确认何时生效。");
      scheduleDrafts.delete(draftKey);
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
    scheduleTriggerDrafts.set(schedule!.id, triggerId);
    setTriggerUncertain(true);
    try {
      const accepted = await mutations.triggerSchedule.mutateAsync({
        id: schedule!.id,
        triggerId,
      });
      if (accepted.status !== "accepted")
        throw new Error("尚未确认执行请求，请使用同一请求重试。");
      setError(null);
      setAcceptedTrigger(true);
      setTriggerUncertain(false);
      scheduleTriggerDrafts.delete(schedule!.id);
      setTriggerId(crypto.randomUUID());
    } catch (e) {
      if (e instanceof ApiRequestError && [400, 404, 422].includes(e.status)) {
        setTriggerUncertain(false);
        scheduleTriggerDrafts.delete(schedule!.id);
      }
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
                  triggerUncertain ||
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
                    changed || parametersDirty ||
                    schedule.desiredDeleted ||
                    mutations.triggerSchedule.isPending
                  }
                  onClick={() => void trigger()}
                >
                  {triggerUncertain ? "确认执行请求" : "立即执行"}
                </Button>
              )}
            </div>
          }
        />
      }
    >
      <FieldGroup>
        <RequestError error={error || packages.error} />
        {validationMessage && <p role="alert" className="text-sm text-destructive">{validationMessage}</p>}
        {(changed || parametersDirty) && <p role="status" className="text-sm">有尚未保存的修改。保存后才会用于自动执行；返回本页可继续编辑，刷新或关闭前请先保存。</p>}
        {schedule && (changed || parametersDirty) && <p className="text-sm">立即执行使用已保存的安排，请先保存本次修改。</p>}
        {savedNotice && !changed && <p role="status" className="text-sm">{savedNotice}</p>}
        {triggerUncertain && <p role="alert">执行请求尚未确认，任务可能已经开始。请点击“确认执行请求”核对，避免重复执行。</p>}
        {schedule && (
          <InventoryStatePanel
            title={
              <ResourceStatusBadge
                label={
                  schedule.desiredDeleted
                    ? "正在停止未来自动执行"
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
              schedule.syncStatus === "synced"
                ? schedule.paused ? "未来自动执行已暂停，当前任务继续运行。" : "将按下方确认的时间自动执行。"
                : schedule.syncStatus === "failed" ? "修改尚未生效，之前的安排可能仍在执行。请核对设置后再次保存，系统也会继续尝试。" : "正在应用修改，之前的安排可能仍在执行。请等待状态确认。"
            }
          />
        )}
        {acceptedTrigger && (
          <InventoryStatePanel
            title="已接受执行请求"
            description="任务正在准备开始，尚不代表任务完成。请在下方执行记录中跟进结果。"
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
            description="暂时不能立即执行。你仍可修改时间或暂停安排；请到任务目录检查此任务。"
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
        <fieldset disabled={creationUncertain || triggerUncertain} className="min-w-0">
          <FieldGroup>
            <TextField
              label="安排名称"
              value={draft.name}
              onChange={(v) => set("name", v)}
            />
            {!schedule && !inherited && (
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
            {workflow && (
              <>
                <div>
                  <LaunchInputs
                    technical={false}
                    key={`${draft.packageKey}/${draft.workflowKey}`}
                    schema={workflow.inputSchema}
                    inputHints={workflow.presentation?.inputHints}
                    value={draft.parameters}
                    onChange={(value) => set("parameters", value)}
                    onDirtyChange={setParametersDirty}
                  />
                </div>
                {parametersDirty && (
                  <p role="alert">
                    业务信息尚未填写完成，请检查后保存安排。
                  </p>
                )}
              </>
            )}
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
            <div className="flex flex-col gap-4">
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
                  label="错过后多久内补做（秒）"
                  type="number"
                  value={String(draft.catchupWindowSeconds)}
                  onChange={(v) => set("catchupWindowSeconds", Number(v))}
                />
            </div>
            <ChoiceField
              label="自动执行状态"
              value={draft.paused ? "paused" : "active"}
              options={[
                { value: "active", label: "启用自动执行" },
                { value: "paused", label: "暂停自动执行" },
              ]}
              onChange={(v) => set("paused", v === "paused")}
            />
            <p className="text-sm text-muted-foreground">
              暂停只停止未来自动执行，不会取消当前任务。每次执行使用当时已保存的任务和连接，已有结果保持不变。
            </p>
          </FieldGroup>
        </fieldset>
        {schedule && (
          <>
            <AppliedSchedulePreview
              id={schedule.id}
              revision={schedule.revision}
              syncStatus={schedule.syncStatus}
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
