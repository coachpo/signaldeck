import { Link, useParams } from "react-router";
import { Button } from "@/components/ui/button";
import { WorkspacePageShell } from "@/components/shared/workspace-page-shell";
import { PageContextBar } from "@/components/shared/page-context-bar";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { usePackage } from "@/hooks/use-workflow-platform";
import { RequestError } from "./feedback";

export function LaunchPage() {
  const { packageId } = useParams();
  const query = usePackage(packageId);
  if (query.isPending) return <InventoryStatePanel title="正在读取工作流…" />;
  if (query.error) return <RequestError error={query.error} retry={() => void query.refetch()} />;
  if (!query.data) return <InventoryStatePanel title="工作流暂不可用" />;
  const pkg = query.data;
  return (
    <WorkspacePageShell contextBar={<PageContextBar title="选择要执行的任务" description={pkg.name} />}>
      <div className="flex max-w-3xl flex-col gap-4">
        <p className="text-sm text-muted-foreground">选择任务后填写信息、核对服务，再开始执行。</p>
        {Object.entries(pkg.definition.workflows).map(([key, workflow]) => (
          <section key={key} className="flex flex-wrap items-center justify-between gap-3 border-b border-ui-separator pb-4">
            <div className="flex min-w-0 flex-col gap-1">
              <h2 className="font-medium">{workflow.name || "未命名任务"}</h2>
              {workflow.description && <p className="text-sm text-muted-foreground">{workflow.description}</p>}
            </div>
            <Button asChild>
              <Link to={`/tasks/new?packageKey=${encodeURIComponent(pkg.key)}&workflowKey=${encodeURIComponent(key)}`}>
                填写{workflow.name || "任务"}
              </Link>
            </Button>
          </section>
        ))}
      </div>
    </WorkspacePageShell>
  );
}
