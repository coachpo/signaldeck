import { Link } from "react-router";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import type { JsonObject } from "@/lib/types/workflow-platform";
export function CacheProvenance({ metadata }: { metadata: JsonObject }) {
  const value = metadata.cacheProvenance;
  if (
    !value ||
    typeof value !== "object" ||
    Array.isArray(value) ||
    typeof value.hit !== "boolean" ||
    typeof value.sourceRunId !== "string" ||
    typeof value.sourceOperationId !== "string" ||
    typeof value.fetchedAt !== "string" ||
    typeof value.expiresAt !== "string" ||
    typeof value.cacheKey !== "string"
  )
    return null;
  return (
    <section
      aria-label="Cache provenance"
      className="flex flex-col gap-2 rounded-lg bg-ui-surface-grouped p-3"
    >
      <ResourceStatusBadge
        label={value.hit ? "Cross-run cache reused" : "Fresh tool result"}
      />
      <p className="text-sm">
        Source{" "}
        <Link
          className="underline"
          to={`/runs/${encodeURIComponent(value.sourceRunId)}`}
        >
          {value.sourceRunId}
        </Link>{" "}
        · operation{" "}
        <code className="break-all text-xs">{value.sourceOperationId}</code>
      </p>
      <p className="text-sm text-muted-foreground">
        Fetched {value.fetchedAt} · cache expiry {value.expiresAt}
      </p>
      <code className="break-all text-xs">{value.cacheKey}</code>
    </section>
  );
}
