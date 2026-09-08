import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import {
  Field,
  FieldGroup,
  TextField,
  ChoiceField,
} from "@/components/shared/form-field";
import {
  usePlatformSchedule,
  usePackages,
  usePlatformMutations,
} from "@/hooks/use-workflow-platform";
import {
  initialParameters,
  parseParameters,
} from "@/lib/platform-authoring/parameter-values";
import { validateLaunchValueForSchema } from "@/lib/platform-authoring/schema/launch-input-state";
import type { Schedule, ScheduleConfig } from "@/lib/types/workflow-platform";
import { ScheduleFireHistory } from "./schedule-fire-history";
import { RequestError } from "./feedback";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { ConfirmDeleteDialog } from "@/components/shared/confirm-delete-dialog";
export function SchedulePage() {
  const { scheduleId } = useParams();
  const query = usePlatformSchedule(scheduleId);
  if (scheduleId && query.isPending)
    return <InventoryStatePanel title="Loading schedule…" />;
  if (scheduleId && !query.data)
    return (
      <RequestError error={query.error} retry={() => void query.refetch()} />
    );
  return <ScheduleEditor key={scheduleId ?? "new"} schedule={query.data} />;
}
function ScheduleEditor({ schedule }: { schedule?: Schedule }) {
  const packages = usePackages();
  const mutations = usePlatformMutations();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<ScheduleConfig>(
    schedule ?? {
      name: "",
      packageKey: "",
      workflowKey: "",
      parameters: null,
      cron: "0 9 * * *",
      timeZone: "UTC",
      overlapPolicy: "skip",
      catchupWindowSeconds: 60,
      paused: false,
    },
  );
  const [parameters, setParameters] = useState(
    JSON.stringify(draft.parameters, null, 2),
  );
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
      const value = parseParameters(parameters);
      const issues = workflow
        ? validateLaunchValueForSchema(workflow.inputSchema, value)
        : [];
      if (issues.length)
        throw new Error(issues.map((i) => `${i.field}: ${i.issue}`).join("; "));
      const saved = await mutations.saveSchedule.mutateAsync({
        ...draft,
        parameters: value,
      });
      setDraft(saved);
      navigate(`/scheduled-tasks/${encodeURIComponent(saved.id)}`);
    } catch (e) {
      setError(e);
    }
  }
  async function trigger() {
    try {
      const accepted = await mutations.triggerSchedule.mutateAsync({
        id: schedule!.id,
        triggerId,
      });
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
          title={schedule?.name ?? "New Scheduled Task"}
          description={
            draft.packageKey
              ? `${draft.packageKey} / ${draft.workflowKey}`
              : "Choose a saved workflow and its timing policy."
          }
          actions={
            <div className="flex flex-wrap gap-2">
              <Button
                disabled={
                  !draft.name ||
                  (!schedule && !workflow) ||
                  mutations.saveSchedule.isPending
                }
                onClick={() => void save()}
              >
                Save schedule
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
                  Run now
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
                    ? `Deletion ${schedule.syncStatus}`
                    : `Schedule ${schedule.syncStatus}`
                }
                tone={schedule.syncStatus === "failed" ? "danger" : "neutral"}
              />
            }
            description={
              schedule.syncErrorCode ??
              (schedule.syncStatus === "synced"
                ? `Applied revision ${schedule.syncedRevision}`
                : `Revision ${schedule.revision} is not yet applied to execution.`)
            }
          />
        )}
        {acceptedTrigger && (
          <InventoryStatePanel
            title="Trigger accepted"
            description={`Trigger ${acceptedTrigger} is queued for execution.`}
            action={
              <Button asChild variant="outline">
                <Link to="/runs">Inspect runs</Link>
              </Button>
            }
          />
        )}
        {schedule && !workflow && (
          <InventoryStatePanel
            tone="warning"
            title="Saved workflow is unavailable"
            description="Run now is unavailable. Timing and pause settings can still be saved."
          />
        )}
        <TextField
          label="Schedule name"
          value={draft.name}
          onChange={(v) => set("name", v)}
        />
        <ChoiceField
          label="Package"
          value={draft.packageKey}
          disabled={!!schedule}
          options={(packages.data?.items ?? []).map((p) => ({
            value: p.key,
            label: p.name,
          }))}
          onChange={(v) => {
            setDraft((d) => ({ ...d, packageKey: v, workflowKey: "" }));
            setParameters("{}");
          }}
        />
        <ChoiceField
          label="Workflow"
          value={draft.workflowKey}
          disabled={!!schedule}
          options={Object.entries(pkg?.definition.workflows ?? {}).map(
            ([value, w]) => ({ value, label: w.name || value }),
          )}
          onChange={(v) => {
            set("workflowKey", v);
            setParameters(
              JSON.stringify(
                pkg?.definition.workflows[v]
                  ? initialParameters(pkg.definition.workflows[v].inputSchema)
                  : null,
                null,
                2,
              ),
            );
          }}
        />
        <TextField
          label="Cron expression"
          value={draft.cron}
          onChange={(v) => set("cron", v)}
        />
        <TextField
          label="IANA timezone"
          value={draft.timeZone}
          onChange={(v) => set("timeZone", v)}
        />
        <ChoiceField
          label="Overlap policy"
          value={draft.overlapPolicy}
          options={[
            { value: "skip", label: "Skip while previous run is active" },
            {
              value: "buffer_one",
              label: "Buffer one trigger until previous run ends",
            },
            { value: "allow", label: "Allow concurrent runs" },
          ]}
          onChange={(v) =>
            set("overlapPolicy", v as ScheduleConfig["overlapPolicy"])
          }
        />
        <TextField
          label="Missed trigger catch-up window (seconds; older triggers are skipped)"
          type="number"
          value={String(draft.catchupWindowSeconds)}
          onChange={(v) => set("catchupWindowSeconds", Number(v))}
        />
        <ChoiceField
          label="Schedule status"
          value={draft.paused ? "paused" : "active"}
          options={[
            { value: "active", label: "Active" },
            { value: "paused", label: "Paused" },
          ]}
          onChange={(v) => set("paused", v === "paused")}
        />
        <Field label="Schedule parameters JSON">
          <Textarea
            aria-label="Schedule parameters JSON"
            value={parameters}
            onChange={(e) => setParameters(e.target.value)}
            className="min-h-40 font-mono text-xs"
          />
        </Field>
        {schedule && (
          <>
            <ScheduleFireHistory scheduleId={schedule.id} />
            <p className="text-sm text-muted-foreground">
              Each fire has an independent identity. Existing runs retain their
              schedule provenance.
            </p>
            <Button variant="destructive" onClick={() => setDeleteOpen(true)}>
              Delete schedule
            </Button>
            <ConfirmDeleteDialog
              open={deleteOpen}
              onOpenChange={setDeleteOpen}
              title="Delete schedule?"
              description="Future triggers stop. Existing runs retain their schedule provenance."
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
