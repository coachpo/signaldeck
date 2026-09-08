import { findArtifacts } from "./artifact-references";
import { runSearch } from "./result-navigation";
import { Link, useSearchParams } from "react-router";
import { Button } from "@/components/ui/button";
import { FieldGroup } from "@/components/shared/form-field";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import { StructuredValueInspector } from "@/components/platform-authoring/inspectors/structured-value-inspector";
import { ExactJsonPreview } from "@/components/platform-authoring/inspectors/exact-json-preview";
import { workflowPlatformApi } from "@/lib/api/workflow-platform";
import type { ExecutionEvidence, Json } from "@/lib/types/workflow-platform";
import { useArtifact } from "@/hooks/use-workflow-platform";
import { useState } from "react";
import { RequestError } from "./feedback";
import { CopyButton } from "@/components/shared/copy-button";

export function ArtifactValue({
  value,
  label,
}: {
  value: Json;
  label: string;
}) {
  const [error, setError] = useState<unknown>(null);
  const refs = findArtifacts(value);
  const [selectedDigest, setSelectedDigest] = useState<string>();
  const activeDigest = refs.some((item) => item.ref.digest === selectedDigest)
    ? selectedDigest
    : undefined;
  const artifact = useArtifact(activeDigest);
  return (
    <FieldGroup>
      <RequestError error={error || artifact.error} />
      {refs.map(({ path, ref }) => (
        <div key={path} className="flex min-w-0 flex-wrap items-center gap-2">
          <code className="break-all text-xs">
            {path} → {ref.digest}
          </code>
          <span className="text-xs text-muted-foreground">
            {ref.mediaType} · {ref.sizeBytes} bytes
          </span>
          {(ref.mediaType.startsWith("text/") ||
            ref.mediaType.includes("json")) && (
            <Button
              variant="outline"
              onClick={() => setSelectedDigest(ref.digest)}
            >
              Inspect artifact
            </Button>
          )}
          <Button
            variant="outline"
            onClick={() =>
              void workflowPlatformApi
                .downloadArtifact(ref.digest)
                .catch(setError)
            }
          >
            Download artifact
          </Button>
        </div>
      ))}
      {activeDigest && (
        <section aria-label="Artifact content" className="flex flex-col gap-2">
          <code className="break-all text-xs">{activeDigest}</code>
          {artifact.isPending ? (
            <p>Loading artifact…</p>
          ) : (
            artifact.data !== undefined && (
              <ExactJsonPreview
                ariaLabel="Artifact content text"
                value={artifact.data}
              />
            )
          )}
        </section>
      )}
      <StructuredValueInspector label={label} value={value} />
      <ExactJsonPreview
        ariaLabel={`${label} JSON`}
        value={JSON.stringify(value, null, 2)}
      />
    </FieldGroup>
  );
}
export function EvidenceTree({
  evidence,
  selected,
}: {
  evidence: ExecutionEvidence[];
  selected?: string | null;
}) {
  const [search] = useSearchParams();
  const ids = new Set(evidence.map((e) => e.id));
  const roots = evidence.filter((e) => !e.parentId || !ids.has(e.parentId));
  const childrenByParent = new Map<string, ExecutionEvidence[]>();
  for (const item of evidence) {
    if (item.parentId) {
      const siblings = childrenByParent.get(item.parentId) ?? [];
      siblings.push(item);
      childrenByParent.set(item.parentId, siblings);
    }
  }
  function rows(items: ExecutionEvidence[], ancestors: Set<string>) {
    return (
      <ul className="flex flex-col gap-2">
        {items
          .filter((e) => !ancestors.has(e.id))
          .map((e) => (
            <li key={e.id} className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  asChild
                  variant={selected === e.id ? "secondary" : "outline"}
                >
                  <Link
                    to={`?${runSearch(search, { tab: "evidence", target: e.id })}`}
                  >
                    {e.kind} · {e.nodeId} · attempt {e.attempt}
                  </Link>
                </Button>
                <ResourceStatusBadge
                  label={e.status}
                  tone={e.status === "failed" ? "danger" : "neutral"}
                />
                <CopyButton
                  value={e.id}
                  text="复制证据 ID"
                  label={`复制证据 ID ${e.id}`}
                />
                {e.operationId && (
                  <CopyButton
                    value={e.operationId}
                    text="复制操作 ID"
                    label={`复制操作 ID ${e.operationId}`}
                  />
                )}
                {e.operationId && (
                  <code className="break-all text-xs">{e.operationId}</code>
                )}
              </div>
              <div className="ml-4 border-l border-ui-separator pl-3">
                {rows(
                  childrenByParent.get(e.id) ?? [],
                  new Set([...ancestors, e.id]),
                )}
              </div>
            </li>
          ))}
      </ul>
    );
  }
  return <div aria-label="Call ownership tree">{rows(roots, new Set())}</div>;
}
