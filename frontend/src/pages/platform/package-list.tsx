import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { ResourceTableFrame } from "@/components/shared/resource-table-frame";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { usePackages } from "@/hooks/use-workflow-platform";
import { RequestError } from "./feedback";

export function PackagesPage() {
  const packages = usePackages();
  return (
    <InventoryPageShell
      pageContext={{
        title: "Workflow Packages",
        description: "Reusable Agents and declarative workflows",
        actions: (
          <Button asChild>
            <Link to="/workflow-packages/new">New package</Link>
          </Button>
        ),
      }}
    >
      <RequestError
        error={packages.error}
        retry={() => void packages.refetch()}
      />
      {packages.isPending ? (
        <InventoryStatePanel title="Loading packages…" />
      ) : packages.data?.items.length ? (
        <ResourceTableFrame>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Package</TableHead>
                <TableHead>Workflows</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {packages.data.items.map((pkg) => (
                <TableRow key={pkg.key}>
                  <TableCell>
                    <strong>{pkg.name}</strong>
                    <p className="text-xs text-muted-foreground">{pkg.key}</p>
                  </TableCell>
                  <TableCell>
                    {Object.keys(pkg.definition.workflows).join(", ")}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button asChild variant="outline">
                        <Link
                          to={`/workflow-packages/${encodeURIComponent(pkg.key)}`}
                        >
                          Open
                        </Link>
                      </Button>
                      <Button asChild>
                        <Link
                          to={`/workflow-packages/${encodeURIComponent(pkg.key)}/run`}
                        >
                          Launch
                        </Link>
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </ResourceTableFrame>
      ) : (
        <InventoryStatePanel
          title="No packages"
          description="Create a package or paste a YAML definition in the editor."
        />
      )}
    </InventoryPageShell>
  );
}
