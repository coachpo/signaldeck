import { ApiRequestError } from "@/lib/api-client";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { Button } from "@/components/ui/button";
export function RequestError({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  if (!error) return null;
  return (
    <InventoryStatePanel
      tone="danger"
      title={error instanceof Error ? error.message : "Request failed"}
      description={
        error instanceof ApiRequestError ? (
          <>
            <span>{error.code}</span>
            {error.details.map((d, i) => (
              <p key={i}>{Object.values(d).join(" · ")}</p>
            ))}
          </>
        ) : undefined
      }
      action={
        retry ? (
          <Button variant="outline" onClick={retry}>
            Retry
          </Button>
        ) : undefined
      }
    />
  );
}
