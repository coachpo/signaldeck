import { userFacingError } from "@/lib/user-facing-error";
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
  const notice = userFacingError(error);
  return (
    <InventoryStatePanel
      tone="danger"
      title={notice.title}
      description={notice.description}
      action={
        retry ? (
          <Button variant="outline" onClick={retry}>
            重试
          </Button>
        ) : undefined
      }
    />
  );
}
