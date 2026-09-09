import { useState } from "react";
import { ApiRequestError } from "@/lib/api-client";
import { useNavigate, useSearchParams } from "react-router";
import { usePackages } from "@/hooks/use-workflow-platform";
import {
  useTaskMutations,
  useTaskPresets,
  useTaskReuse,
  useTaskPreparation,
} from "@/hooks/use-task-experience";
import { useDisplayMode } from "@/hooks/use-display-mode";
import { Button } from "@/components/ui/button";
import { TextField } from "@/components/shared/form-field";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { RequestError } from "./feedback";
import { TaskConnections } from "./task-connections";
import { TaskPreparation } from "./task-preparation";
import { LaunchInputs } from "./launch-inputs";
import {
  taskDefaults,
  taskConstraintErrors,
} from "./task-catalog";
import type { Json, JsonObject, WorkflowDefinition } from "@/lib/types/workflow-platform";
import type {
  Preparation,
  ReuseInput,
  TaskPreset,
} from "@/lib/types/task-experience";
import { validateLaunchValueForSchema } from "@/lib/platform-authoring/schema/launch-input-state";

export function TaskPage() {
  const [params] = useSearchParams();
  const packages = usePackages();
  const presets = useTaskPresets();
  const fromRun = params.get("fromRun") ?? undefined;
  const reuse = useTaskReuse(fromRun);
  const presetId = params.get("presetId");
  const preset = presets.data?.items.find((p) => p.id === presetId);
  const historical = reuse.data;
  const packageKey =
    historical?.packageKey ??
    preset?.packageKey ??
    params.get("packageKey") ??
    "";
  const workflowKey =
    historical?.workflowKey ??
    preset?.workflowKey ??
    params.get("workflowKey") ??
    "";
  const pkg = packages.data?.items.find((p) => p.key === packageKey);
  const workflow = pkg?.definition.workflows[workflowKey];
  if (
    packages.isPending ||
    (fromRun && reuse.isPending) ||
    (presetId && presets.isPending)
  )
    return <InventoryStatePanel title="正在读取任务…" />;
  if (packages.error || reuse.error || (presetId && presets.error))
    return (
      <RequestError error={packages.error ?? reuse.error ?? presets.error} />
    );
  if ((!historical && (!pkg || !workflow)) || (presetId && !preset))
    return (
      <InventoryStatePanel
        title="无法找到任务"
        description="定义或常用配置可能已删除。可以返回任务列表选择其他任务。"
      />
    );
  const schema = historical?.inputSchema ?? workflow!.inputSchema;
  return (
    <TaskForm
      key={`${packageKey}/${workflowKey}/${historical?.sourceRunId ?? presetId ?? "new"}`}
      packageKey={packageKey}
      workflowKey={workflowKey}
      packageHash={historical?.packageHash ?? pkg!.packageHash}
      schema={schema}
      workflow={historical?.workflow ?? workflow}
      initial={
        historical ? historical.parameters : preset?.hasParameters ? preset.parameters : taskDefaults(schema)
      }
      historical={historical}
      preset={preset}
    />
  );
}
const drafts = new Map<
  string,
  {
    parameters: Json;
    launchId: string;
    uncertain?: boolean;
    prepared?: Preparation | null;
  }
>();
function TaskForm({
  packageKey,
  workflowKey,
  packageHash,
  schema,
  workflow,
  initial,
  historical,
  preset,
}: {
  packageKey: string;
  workflowKey: string;
  packageHash: string;
  schema: JsonObject;
  workflow?: WorkflowDefinition;
  initial: Json;
  historical?: ReuseInput;
  preset?: TaskPreset;
}) {
  const descriptor = { title: workflow?.name || workflowKey, description: workflow?.description };
  const { expert } = useDisplayMode();
  const navigate = useNavigate();
  const mutations = useTaskMutations();
  const draftKey = `${packageKey}/${workflowKey}/${packageHash}/${historical?.sourceRunId ?? preset?.id ?? "new"}`;
  const [draft, setDraft] = useState(
    () =>
      drafts.get(draftKey) ?? {
        parameters: initial,
        launchId: crypto.randomUUID(),
      },
  );
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [name, setName] = useState(preset?.name ?? "");
  const [saved, setSaved] = useState(false);
  const [uncertain, setUncertain] = useState(draft.uncertain ?? false);
  const [initialRevision] = useState(packageHash);
  const parameters = draft.parameters;
  function change(value: Json) {
    const next = { parameters: value, launchId: crypto.randomUUID() };
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
    ...(historical ? { sourceRunId: historical.sourceRunId } : {}),
  };
  function validationErrors() {
    const issues = validateLaunchValueForSchema(schema, parameters);
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
  async function launch() {
    if (!validate()) return;
    let checked = prepared;
    if (!checked) {
      const refreshed = await preparation.refetch();
      checked = refreshed.data;
      // New binding changes need a visible review before they can be confirmed.
      if (checked?.changedBindings.length) return;
    }
    if (!checked?.ready || !checked.bindingToken) return;
    try {
      setError(null);
      setUncertain(true);
      const submitted = { ...draft, uncertain: true, prepared: checked };
      setDraft(submitted);
      drafts.set(draftKey, submitted);
      const run = await mutations.launch.mutateAsync({
        ...body,
        launchId: draft.launchId,
        bindingToken: checked.bindingToken,
      });
      drafts.delete(draftKey);
      navigate(`/runs/${encodeURIComponent(run.id)}`);
    } catch (e) {
      if (e instanceof ApiRequestError && e.status >= 400 && e.status < 500) {
        setUncertain(false);
        const rejected = { ...draft, uncertain: false, prepared: null };
        setDraft(rejected);
        drafts.set(draftKey, rejected);
        void preparation.refetch();
      }
      setError(e);
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
      {initialRevision !== packageHash && <p role="alert">任务定义已更新，填写内容保持原样。请重新核对所有输入与连接设置后开始。</p>}
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
              disabled={dirty || mutations.launch.isPending || (!uncertain && (preparation.isFetching || !!prepared && prepared.packageHash !== packageHash))}
              onClick={() => void launch()}
            >
              {mutations.launch.isPending
                ? "正在提交…"
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
        <details>
          <summary className="cursor-pointer text-sm font-medium">
            保存常用输入或收藏任务（可选）
          </summary>
          <div className="flex flex-col gap-3 pt-3">
            <TextField label="配置名称" value={name} onChange={setName} />
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
