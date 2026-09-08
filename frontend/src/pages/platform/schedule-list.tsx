import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardDescription,
} from "@/components/ui/card";
import { usePlatformSchedules } from "@/hooks/use-workflow-platform";
import { RequestError } from "./feedback";

export function SchedulesPage() {
  const schedules = usePlatformSchedules();
  return (
    <InventoryPageShell
      pageContext={{
        title: "Scheduled Tasks",
        description: "Timezone-aware workflow launches",
        actions: (
          <Button asChild>
            <Link to="/scheduled-tasks/new">New schedule</Link>
          </Button>
        ),
      }}
    >
      <div className="flex flex-col gap-3">
        <RequestError
          error={schedules.error}
          retry={() => void schedules.refetch()}
        />
        {schedules.isPending && (
          <InventoryStatePanel title="Loading schedules…" />
        )}
        {schedules.data?.items.map((s) => (
          <Card key={s.id}>
            <CardHeader>
              <CardTitle>{s.name}</CardTitle>
              <CardDescription>
                {s.packageKey} / {s.workflowKey} ·{" "}
                {s.paused ? "Paused" : "Active"} · {s.syncStatus}
                {s.desiredDeleted ? " · deletion pending" : ""}
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap items-center gap-3">
              <span className="text-sm">
                {s.cron} · {s.timeZone} · overlap {s.overlapPolicy}
              </span>
              <Button asChild variant="outline">
                <Link to={`/scheduled-tasks/${encodeURIComponent(s.id)}`}>
                  Open {s.name}
                </Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </InventoryPageShell>
  );
}
