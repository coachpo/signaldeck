import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardDescription,
} from "@/components/ui/card";
import {
  usePackages,
  usePlatformRuns,
  useResources,
} from "@/hooks/use-workflow-platform";
import { RequestError } from "./feedback";
export function DashboardPage() {
  const packages = usePackages();
  const runs = usePlatformRuns();
  const resources = useResources();
  const cards = [
    {
      title: "Workflow Packages",
      count: packages.data?.items.length,
      path: "/workflow-packages",
      description: "Define reusable Agents and DAGs.",
    },
    {
      title: "Runs",
      count: runs.data?.items.length,
      path: "/runs",
      description: "Inspect durable execution and evidence.",
    },
    {
      title: "Resources",
      count: resources.data?.items.length,
      path: "/resources",
      description: "Bind models and tool resources.",
    },
  ];
  return (
    <InventoryPageShell
      pageContext={{ title: "Dashboard", description: "Your Agent workflows" }}
    >
      <RequestError error={packages.error || runs.error || resources.error} />
      <div className="grid gap-4 md:grid-cols-3">
        {cards.map((card) => (
          <Card key={card.path}>
            <CardHeader>
              <CardTitle>{card.title}</CardTitle>
              <CardDescription>{card.description}</CardDescription>
            </CardHeader>
            <CardContent className="flex items-center justify-between gap-2">
              <span className="text-3xl font-semibold">
                {card.count ?? "—"}
              </span>
              <Button asChild variant="outline">
                <Link to={card.path}>Open {card.title}</Link>
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </InventoryPageShell>
  );
}
