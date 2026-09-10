import { useTaskDraftMutations } from "@/hooks/use-task-drafts";
import type { TaskDraft, TaskDraftWrite } from "@/lib/types/task-drafts";
import { useRef, useState } from "react";
import { ApiRequestError } from "@/lib/api-client";
import { useNavigate } from "react-router";
import {
  useTaskMutations,
  useTaskPreparation,
} from "@/hooks/use-task-experience";
import { useDisplayMode } from "@/hooks/use-display-mode";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/shared/form-field";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { RequestError } from "./feedback";
import { TaskConnections } from "./task-connections";
import { TaskPreparation } from "./task-preparation";
import { LaunchInputs } from "./launch-inputs";
import {
  taskConstraintErrors,
} from "./task-catalog";
import type { Json, JsonObject, WorkflowDefinition } from "@/lib/types/workflow-platform";
import type {
  Preparation,
  ReuseInput,
  TaskPreset,
} from "@/lib/types/task-experience";
import { validateLaunchValueForSchema } from "@/lib/platform-authoring/schema/launch-input-state";

const drafts = new Map<
  string,
  {
    parameters: Json;
    hasParameters?: boolean;
    launchId: string;
    uncertain?: boolean;
    prepared?: Preparation | null;
    jsonText?: string | null;
    serverId?: string;
    serverRevision?: number;
  }
>();
export function TaskForm({
  packageKey,
  workflowKey,
  packageHash,
  schema,
  workflow,
  initial,
  historical,
  preset,
  restored,
  initialLaunchId,
}: {
  packageKey: string;
  workflowKey: string;
  packageHash: string;
  schema: JsonObject;
  workflow?: WorkflowDefinition;
  initial: Json;
  historical?: ReuseInput;
  preset?: TaskPreset;
  restored?: TaskDraft;
  initialLaunchId: string;
}) {
  const descriptor = { title: workflow?.name || workflowKey, description: workflow?.description };
  const { expert } = useDisplayMode();
  const navigate = useNavigate();
  const mutations = useTaskMutations();
  const draftMutations = useTaskDraftMutations();
  const draftKey = `${packageKey}/${workflowKey}/${packageHash}/${restored?.id ?? historical?.sourceRunId ?? preset?.id ?? "new"}`;
  const [draft, setDraft] = useState(
    () =>
      drafts.get(draftKey) ?? {
        parameters: initial,
        hasParameters: restored?.hasParameters ?? true,
        launchId: restored?.launchId ?? initialLaunchId,
        serverId: restored?.id ?? crypto.randomUUID(),
        serverRevision: restored?.revision ?? 0,
        jsonText: restored?.jsonText ?? null,
        uncertain: restored?.pending ?? false,
        prepared: restored?.pending ? { packageKey, workflowKey, packageHash, ready: true, bindingToken: restored.bindingToken, requirements: [], issues: [], changedBindings: [], previousBindings: {}, effectiveSettings: {} } : null,
      },
  );
  const [dirty, setDirty] = useState(draft.jsonText !== null && draft.jsonText !== undefined);
  const [draftChanged, setDraftChanged] = useState(false);
  const [draftNotice, setDraftNotice] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [name, setName] = useState(restored?.name ?? preset?.name ?? "");
  const [saved, setSaved] = useState(false);
  const [uncertain, setUncertain] = useState(draft.uncertain ?? false);
  const [initialRevision] = useState(packageHash);
  const launchInFlight = useRef(false);
  const [launchBusy, setLaunchBusy] = useState(false);
  const parameters = draft.parameters;
  function change(value: Json) {
    const next = { ...draft, parameters: value, hasParameters: true, jsonText: null, uncertain: false, prepared: null };
    setDraftChanged(true);
    setDraft(next);
    drafts.set(draftKey, next);
    setSaved(false);
    setErrors({});
  }
  const body = {
    packageKey,
    workflowKey,
    parameters,
    revisionHash: uncertain && draft.prepared ? draft.prepared.packageHash : packageHash,
    ...((restored?.sourceRunId ?? historical?.sourceRunId) ? { sourceRunId: restored?.sourceRunId ?? historical?.sourceRunId } : {}),
  };
  function validationErrors() {
    const issues = validateLaunchValueForSchema(schema, parameters);
    if (draft.hasParameters === false) return { parameters: "草稿尚未应用输入，请填写或应用 JSON。" };
    return {
      ...Object.fromEntries(issues.map((i) => [i.field, i.issue])),
      ...taskConstraintErrors(schema, parameters),
    };
  }
  const preparation = useTaskPreparation(body, !dirty && !uncertain && Object.keys(validationErrors()).length === 0);
  const prepared = uncertain ? draft.prepared : preparation.data;
  function validate() {
    const allErrors = validationErrors();
    setErrors(allErrors);
    return Object.keys(allErrors).length === 0;
  }
  async function prepare() {
    if (!validate()) return;
    try {
      setError(null);
      await preparation.refetch({ throwOnError: true });
    } catch (e) {
      setError(e);
    }
  }
  function draftPayload(pending = uncertain, token = draft.prepared?.bindingToken ?? null): TaskDraftWrite & { id: string } {
    return {
      id: draft.serverId ?? crypto.randomUUID(), revision: draft.serverRevision ?? 0,
      name: name.trim() || descriptor.title, packageKey, workflowKey, packageHash,
      sourceRunId: restored?.sourceRunId ?? historical?.sourceRunId ?? null,
      hasParameters: draft.hasParameters ?? true, parameters,
      jsonText: draft.jsonText ?? null, launchId: draft.launchId, pending,
      bindingToken: pending ? token : null,
    };
  }
  async function persistDraft() {
    try {
      setError(null);
      const savedDraft = await draftMutations.save.mutateAsync(draftPayload());
      const next = { ...draft, serverId: savedDraft.id, serverRevision: savedDraft.revision };
      setDraft(next); drafts.set(draftKey, next);
      setDraftChanged(false); setDraftNotice(`草稿已保存 · 修订 ${savedDraft.revision}`);
      navigate(`/tasks/new?draftId=${encodeURIComponent(savedDraft.id)}`, { replace: true });
    } catch (e) { setError(e); }
  }
  async function deleteDraft() {
    try {
      await draftMutations.remove.mutateAsync({ id: draft.serverId!, revision: draft.serverRevision! });
      drafts.delete(draftKey); navigate("/tasks");
    } catch (e) { setError(e); }
  }
  async function launch() {
    if (launchInFlight.current || !validate()) return;
    launchInFlight.current = true;
    setLaunchBusy(true);
    try {
      let checked = prepared;
      if (!checked) {
        const refreshed = await preparation.refetch();
        checked = refreshed.data;
        // New binding changes need a visible review before they can be confirmed.
        if (checked?.changedBindings.length) return;
      }
      if (!checked?.ready || !checked.bindingToken) return;
      let receipt: TaskDraft | undefined;
      try {
        setError(null);
        setUncertain(true);
        // Commit the original identity before sending a request whose response may be lost.
        const submitting = { ...draft, uncertain: true, prepared: checked };
        setDraft(submitting); drafts.set(draftKey, submitting);
        receipt = await draftMutations.save.mutateAsync(draftPayload(true, checked.bindingToken));
        const submitted = { ...draft, uncertain: true, prepared: checked, serverId: receipt.id, serverRevision: receipt.revision };
        setDraft(submitted);
        drafts.set(draftKey, submitted);
        navigate(`/tasks/new?draftId=${encodeURIComponent(receipt.id)}`, { replace: true });
        const run = await mutations.launch.mutateAsync({
          ...body,
          launchId: draft.launchId,
          bindingToken: checked.bindingToken,
        });
        await draftMutations.remove.mutateAsync({ id: receipt.id, revision: receipt.revision }).catch(() => undefined);
        drafts.delete(draftKey);
        navigate(`/runs/${encodeURIComponent(run.id)}`);
      } catch (e) {
        if (e instanceof ApiRequestError && e.status >= 400 && e.status < 500) {
          const rejected = { ...draft, uncertain: false, prepared: null, serverRevision: receipt?.revision ?? draft.serverRevision };
          if (receipt) {
            try {
              const released = await draftMutations.save.mutateAsync({ ...draftPayload(false), revision: receipt.revision });
              rejected.serverRevision = released.revision;
            } catch { setError(e); return; }
          }
          setUncertain(false);
          setDraft(rejected);
          drafts.set(draftKey, rejected);
          void preparation.refetch();
        }
        setError(e);
      }
    } finally {
      launchInFlight.current = false;
      setLaunchBusy(false);
    }
  }
  async function save(update: boolean, favorite = false) {
    if (!favorite && !validate()) return;
    try {
      await mutations.savePreset.mutateAsync({
        ...(update && preset ? { id: preset.id } : {}),
        name: name.trim() || descriptor?.title || workflowKey,
        packageKey,
        workflowKey,
        packageHash,
        parameters: favorite ? null : parameters,
        hasParameters: !favorite,
        isFavorite: favorite || preset?.isFavorite || false,
        isPinned: preset?.isPinned || false,
      });
      setSaved(true);
    } catch (e) {
      setError(e);
    }
  }
  return (
    <WorkspacePageShell
      contextBar={
        <PageContextBar
          title={descriptor?.title ?? "执行任务"}
          description={
            historical
              ? "修改输入将创建一次新执行；原结果和原始定义保持不变。"
              : descriptor?.description
          }
        />
      }
    >
      <div className="flex max-w-3xl flex-col gap-5">
        <RequestError error={error || preparation.error} />
      {(restored?.needsRevalidation || initialRevision !== packageHash) && <p role="alert">任务当前定义已更新；草稿保留原定义修订及所有输入，不补默认值。启动仍核对原修订的输入与连接。</p>}
        {Object.keys(errors).length > 0 && (
          <p role="alert" className="text-sm text-destructive">
            请检查以下字段：
            {Object.entries(errors)
              .map(
                ([field, message]) =>
                  `${field.replace("parameters.", "")}：${message}`,
              )
              .join("；")}
          </p>
        )}
        {historical && (
          <p className="text-sm text-muted-foreground">
            使用原结果的定义修订：{packageHash.slice(0, 12)}。新数据会重新获取。
          </p>
        )}
        {preset?.needsRevalidation && (
          <p role="alert">
            该配置来自旧定义。已保留所有输入，请按当前字段重新核对；不支持的字段需要专家处理。
          </p>
        )}
        <fieldset disabled={uncertain} className="min-w-0">
          <div>
            <LaunchInputs
              technical={expert}
              schema={schema}
              inputHints={workflow?.presentation?.inputHints}
              value={parameters}
              onChange={change}
              onDirtyChange={setDirty}
              initialJsonText={draft.jsonText ?? null}
              onJsonTextChange={(jsonText) => {
                setDraft(current => { const next = { ...current, jsonText }; drafts.set(draftKey, next); return next; });
                setDraftChanged(true);
              }}
            />
          </div>
        </fieldset>
        {preparation.isFetching && !uncertain && <p role="status">正在自动核对连接与本次设置…</p>}
        {prepared && (
          <>
            <TaskPreparation preparation={prepared} />
            <TaskConnections
              requirements={prepared.requirements}
              onSaved={() => void prepare()}
            />
          </>
        )}
        <div className="flex flex-wrap gap-2">
          {(expert || dirty || !!error || !!preparation.error || !prepared?.ready) && (
            <Button
              variant="outline"
              disabled={
                dirty ||
                preparation.isFetching ||
                uncertain
              }
              onClick={() => void prepare()}
            >
              {preparation.isFetching ? "正在核对…" : "核对连接与本次设置"}
            </Button>
          )}
          {(!prepared || prepared.ready) && (
            <Button
              disabled={dirty || launchBusy || draftMutations.save.isPending || mutations.launch.isPending || (!uncertain && (preparation.isFetching || !!prepared && prepared.packageHash !== packageHash))}
              onClick={() => void launch()}
            >
              {launchBusy || mutations.launch.isPending
                ? draftMutations.save.isPending ? "正在保存启动请求…" : "正在提交…"
                : uncertain
                  ? "使用同一请求重试"
                  : prepared?.changedBindings.length
                    ? "确认变化并开始"
                    : "开始任务"}
            </Button>
          )}
          <Button
            variant="outline"
            disabled={uncertain || dirty}
            onClick={() =>
              navigate("/scheduled-tasks/new", {
                state: {
                  scheduleInput: {
                    packageKey,
                    workflowKey,
                    parameters,
                    name: descriptor?.title,
                  },
                },
              })
            }
          >
            设置重复执行
          </Button>
        </div>
        {uncertain && (
          <p role="status" className="text-sm">
            请求可能已经受理。重试使用同一请求身份，避免重复执行；核实前请勿修改输入。
          </p>
        )}
        <section className="flex flex-col gap-3" aria-label="任务草稿">
          <TextField label="草稿名称" disabled={uncertain} value={name} onChange={(value) => { setName(value); setDraftChanged(true); }} />
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" disabled={uncertain || launchBusy || draftMutations.save.isPending} onClick={() => void persistDraft()}>保存草稿</Button>
            {!!draft.serverRevision && <Button variant="ghost" disabled={uncertain || draftMutations.remove.isPending} onClick={() => void deleteDraft()}>删除草稿</Button>}
            {error instanceof ApiRequestError && error.status === 409 && <Button variant="outline" onClick={() => window.location.reload()}>恢复服务器草稿（舍弃本页修改）</Button>}
          </div>
          <p className="text-sm text-muted-foreground">草稿保留未完成或未应用的 JSON；保存不会启动任务，也不会创建常用配置。请勿填写资源凭据。</p>
          {draftChanged && <p role="status">有尚未保存的草稿修改。</p>}
          {draftNotice && <p role="status">{draftNotice}</p>}
        </section>
        <details>
          <summary className="cursor-pointer text-sm font-medium">
            保存常用输入或收藏任务（可选）
          </summary>
          <div className="flex flex-col gap-3 pt-3">
            <TextField label="配置名称" disabled={uncertain} value={name} onChange={setName} />
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                disabled={mutations.savePreset.isPending || dirty || uncertain}
                onClick={() => void save(false)}
              >
                保存为新配置
              </Button>
              {preset && (
                <Button
                  variant="outline"
                  disabled={mutations.savePreset.isPending || dirty || uncertain}
                  onClick={() => void save(true)}
                >
                  更新此配置
                </Button>
              )}
              <Button variant="ghost" disabled={uncertain} onClick={() => void save(false, true)}>
                仅收藏任务，不保存输入
              </Button>
            </div>
            {saved && (
              <p role="status">
                已保存，可在任务首页找回。保存不会启动任务或创建计划。
              </p>
            )}
          </div>
        </details>
      </div>
    </WorkspacePageShell>
  );
}
