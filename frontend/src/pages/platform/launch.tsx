import { useState } from "react";
import { useNavigate, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, ChoiceField } from "@/components/shared/form-field";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import {
  usePackage,
  usePlatformMutations,
} from "@/hooks/use-workflow-platform";
import type { Json, WorkflowPackage } from "@/lib/types/workflow-platform";
import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import { RequestError } from "./feedback";
import { initialParameters } from "@/lib/platform-authoring/parameter-values";
import { LaunchInputs } from "./launch-inputs";
export function LaunchPage() {
  const { packageId } = useParams();
  const query = usePackage(packageId);
  if (query.isPending)
    return <InventoryStatePanel title="Loading saved package…" />;
  if (!query.data)
    return (
      <RequestError error={query.error} retry={() => void query.refetch()} />
    );
  return <LaunchForm key={query.data.packageHash} pkg={query.data} />;
}
function LaunchForm({ pkg }: { pkg: WorkflowPackage }) {
  const [workflowKey, setWorkflowKey] = useState("");
  const [dirty, setDirty] = useState(false);
  const [parameters, setParameters] = useState<Json>(null);
  const [error, setError] = useState<unknown>(null);
  const [launchId] = useState(() => crypto.randomUUID());
  const { launch } = usePlatformMutations();
  const navigate = useNavigate();
  const workflow = pkg.definition.workflows[workflowKey];
  async function submit() {
    try {
      const run = await launch.mutateAsync({
        key: pkg.key,
        workflowKey,
        parameters,
        launchId,
      });
      navigate(`/runs/${encodeURIComponent(run.id)}`);
    } catch (e) {
      setError(e);
    }
  }
  return (
    <WorkspacePageShell
      contextBar={
        <PageContextBar
          title={`Launch ${pkg.name}`}
          description="Runs use the saved definition and immutable resource bindings."
          actions={
            <Button
              disabled={!workflow || dirty || launch.isPending}
              onClick={() => void submit()}
            >
              Start run
            </Button>
          }
        />
      }
    >
      <FieldGroup>
        <RequestError error={error} />
        <ChoiceField
          label="Workflow"
          value={workflowKey}
          options={Object.entries(pkg.definition.workflows).map(
            ([value, w]) => ({ value, label: w.name || value }),
          )}
          onChange={(key) => {
            setWorkflowKey(key);
            setParameters(
              initialParameters(pkg.definition.workflows[key].inputSchema),
            );
            setDirty(false);
            setError(null);
          }}
        />
        {workflow && (
          <>
            <Field label="Input schema">
              <ExactJsonPreview
                ariaLabel="Workflow input schema"
                value={JSON.stringify(workflow.inputSchema, null, 2)}
              />
            </Field>
            <LaunchInputs
              key={workflowKey}
              schema={workflow.inputSchema}
              value={parameters}
              onChange={setParameters}
              onDirtyChange={setDirty}
            />
          </>
        )}
      </FieldGroup>
    </WorkspacePageShell>
  );
}
