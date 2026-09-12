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
        title: "制作工作流",
        description: "安排任务步骤，复用助手和服务，制作自己的任务流程。",
        actions: (
          <Button asChild>
            <Link to="/workflow-packages/new">新建工作流集</Link>
          </Button>
        ),
      }}
    >
      <RequestError
        error={packages.error}
        retry={() => void packages.refetch()}
      />
      {packages.isPending ? (
        <InventoryStatePanel title="正在读取工作流…" />
      ) : packages.data?.items.length ? (
        <ResourceTableFrame>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>工作流集</TableHead>
                <TableHead>任务流程</TableHead>
                <TableHead>操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {packages.data.items.map((pkg) => (
                <TableRow key={pkg.key}>
                  <TableCell>
                    <strong>{pkg.name}</strong>
                    <p className="text-xs text-muted-foreground">{pkg.description}</p>
                  </TableCell>
                  <TableCell>
                    {Object.values(pkg.definition.workflows).map((workflow, index) => workflow.name || `任务流程 ${index + 1}`).join("、")}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-2">
                      <Button asChild variant="outline">
                        <Link
                          to={`/workflow-packages/${encodeURIComponent(pkg.key)}`}
                        >
                          编辑
                        </Link>
                      </Button>
                      <Button asChild>
                        <Link
                          to={`/workflow-packages/${encodeURIComponent(pkg.key)}/run`}
                        >
                          开始任务
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
          title="还没有工作流"
          description="新建一个工作流集，填写任务说明、选择助手并安排步骤。也可以导入已有工作流。"
        />
      )}
    </InventoryPageShell>
  );
}
