import { useEffect, useRef, useState } from "react";
import { Link, useBlocker, useNavigate, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import {
  usePackage,
  usePlatformMutations,
} from "@/hooks/use-workflow-platform";
import { initialPackageSource } from "@/lib/platform-authoring/package-source";
import type {
  ValidationResult,
  WorkflowPackage,
} from "@/lib/types/workflow-platform";
import { DependencyGraph } from "./dependency-graph";
import { PackageStructure } from "./package-structure";
import { RequestError } from "./feedback";

export function PackageEditorPage() {
  const { packageId } = useParams();
  const query = usePackage(packageId);
  if (packageId && query.isPending)
    return <InventoryStatePanel title="Loading package…" />;
  if (packageId && !query.data)
    return (
      <RequestError error={query.error} retry={() => void query.refetch()} />
    );
  return <PackageEditor key={packageId ?? "new"} pkg={query.data} />;
}
function PackageEditor({ pkg }: { pkg?: WorkflowPackage }) {
  const [source, setSource] = useState(pkg?.source ?? initialPackageSource);
  const [savedSource, setSavedSource] = useState(
    pkg?.source ?? initialPackageSource,
  );
  const [validation, setValidation] = useState<{
    source: string;
    result: ValidationResult;
  } | null>(null);
  const [tab, setTab] = useState("source");
  const sourceRef = useRef<HTMLTextAreaElement>(null);
  const navigate = useNavigate();
  const mutations = usePlatformMutations();
  const [sectionDrafts, setSectionDrafts] = useState({
    agents: false,
    workflows: false,
  });
  const unapplied = sectionDrafts.agents || sectionDrafts.workflows;
  const dirty = source !== savedSource || unapplied;
  const saveNavigation = useRef(false);
  const blocker = useBlocker(() => dirty && !saveNavigation.current);
  useEffect(() => {
    if (!dirty) return;
    const prevent = (e: BeforeUnloadEvent) => e.preventDefault();
    window.addEventListener("beforeunload", prevent);
    return () => window.removeEventListener("beforeunload", prevent);
  }, [dirty]);
  const currentValidation =
    validation?.source === source ? validation.result : null;
  const plans =
    currentValidation?.plans ?? (source === pkg?.source ? pkg.plans : null);
  async function validate() {
    const result = await mutations.validate.mutateAsync(source);
    setValidation({ source, result });
  }
  async function save() {
    const result = await mutations.validate.mutateAsync(source);
    setValidation({ source, result });
    if (result.diagnostics.length || !result.definition || !result.plans)
      return;
    const saved = await mutations.savePackage.mutateAsync({
      source,
      key: pkg?.key,
    });
    setSource(saved.source);
    setSavedSource(saved.source);
    if (!pkg) {
      saveNavigation.current = true;
      navigate(`/workflow-packages/${encodeURIComponent(saved.key)}`);
    }
  }
  const busy = mutations.validate.isPending || mutations.savePackage.isPending;
  return (
    <WorkspacePageShell
      contextBar={
        <PageContextBar
          title={pkg?.name ?? "New Workflow Package"}
          description={
            dirty
              ? "Unsaved changes"
              : pkg
                ? "Saved definition"
                : "New definition"
          }
          actions={
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                disabled={busy || unapplied}
                onClick={() => void validate().catch(() => {})}
              >
                Validate graph
              </Button>
              <Button
                disabled={busy || unapplied}
                onClick={() => void save().catch(() => {})}
              >
                Save package
              </Button>
              {pkg && (
                <Button asChild variant="outline">
                  <Link
                    to={`/workflow-packages/${encodeURIComponent(pkg.key)}/run`}
                  >
                    Launch saved package
                  </Link>
                </Button>
              )}
            </div>
          }
        />
      }
    >
      <div className="flex flex-col gap-4">
        <RequestError
          error={mutations.validate.error || mutations.savePackage.error}
        />
        {blocker.state === "blocked" && (
          <InventoryStatePanel
            tone="warning"
            title="Leave unsaved changes?"
            description="Launch uses the last saved package. Leaving discards this draft."
            action={
              <>
                <Button onClick={() => blocker.proceed()}>
                  Leave without saving
                </Button>
                <Button variant="outline" onClick={() => blocker.reset()}>
                  Keep editing
                </Button>
              </>
            }
          />
        )}
        {unapplied && (
          <InventoryStatePanel
            tone="warning"
            title="Apply the structural JSON draft before saving or validating"
          />
        )}
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList>
            <TabsTrigger value="source" disabled={unapplied}>
              YAML
            </TabsTrigger>
            <TabsTrigger value="structure">Structure</TabsTrigger>
            <TabsTrigger value="graph">Graph</TabsTrigger>
          </TabsList>
          <TabsContent
            value="source"
            forceMount
            className="data-[state=inactive]:hidden"
          >
            <Textarea
              ref={sourceRef}
              aria-label="Workflow Package YAML"
              value={source}
              onChange={(e) => setSource(e.target.value)}
              spellCheck={false}
              className="min-h-96 font-mono text-xs"
            />
          </TabsContent>
          <TabsContent
            value="structure"
            forceMount
            className="data-[state=inactive]:hidden"
          >
            <PackageStructure
              source={source}
              onChange={setSource}
              onDraftChange={(section, dirty) =>
                setSectionDrafts((d) => ({ ...d, [section]: dirty }))
              }
            />
          </TabsContent>
          <TabsContent value="graph">
            {plans ? (
              <div className="flex flex-col gap-4">
                {Object.values(plans).map((plan) => (
                  <DependencyGraph key={plan.workflowKey} plan={plan} />
                ))}
              </div>
            ) : (
              <InventoryStatePanel title="Validate the current definition to inspect its graph" />
            )}
          </TabsContent>
        </Tabs>
        {currentValidation && (
          <InventoryStatePanel
            title={
              currentValidation.diagnostics.length
                ? "Definition needs attention"
                : "Definition validated"
            }
            description={currentValidation.diagnostics.map((d, i) => (
              <p key={i}>
                <Button
                  variant="link"
                  onClick={(event) => {
                    const trigger = event.currentTarget;
                    setTab("source");
                    requestAnimationFrame(() => {
                      const input = sourceRef.current;
                      const active = document.activeElement;
                      if (
                        !trigger.isConnected ||
                        (active !== trigger && active !== document.body)
                      )
                        return;
                      if (input && input.value === source) {
                        const offset = Math.min(
                          source.length,
                          source
                            .split("\n")
                            .slice(0, Math.max(0, (d.line ?? 1) - 1))
                            .reduce((sum, line) => sum + line.length + 1, 0) +
                            Math.max(0, (d.column ?? 1) - 1),
                        );
                        input.focus();
                        input.setSelectionRange(offset, offset);
                      }
                    });
                  }}
                >
                  {d.path}
                  {d.line ? ` · line ${d.line}:${d.column ?? 1}` : ""}
                </Button>
                {d.code}: {d.message}
              </p>
            ))}
          />
        )}
      </div>
    </WorkspacePageShell>
  );
}
