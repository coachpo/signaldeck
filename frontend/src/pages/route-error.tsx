import { Link, isRouteErrorResponse, useRouteError } from "react-router";
import { AlertTriangle, Home } from "lucide-react";
import { CanonicalErrorPage } from "@/components/shared/canonical-error-page";
import { Button } from "@/components/ui/button";

export function RouteErrorPage() {
  const error = useRouteError();
  const missing = isRouteErrorResponse(error) && error.status === 404;
  return (
    <CanonicalErrorPage
      action={<>
        <Button variant="outline" onClick={() => window.location.reload()}>重新加载</Button>
        <Button asChild size="sm"><Link to="/"><Home data-icon="inline-start" />返回任务首页</Link></Button>
      </>}
      contentTestId="route-error-content"
      description="已保存的任务和结果仍然保留。"
      descriptionTestId="route-error-description"
      icon={<AlertTriangle className="size-4 text-destructive" />}
      meta={null}
      metaTestId="route-error-meta"
      panelDescription={missing ? "这项内容可能已经移除。请返回首页选择任务，或在结果页查找历史记录。" : "可以重新加载此页；若仍无法打开，请返回首页。正在执行的任务不受页面关闭影响。"}
      panelTestId="route-error-panel"
      panelTitle="继续处理任务"
      rootElement="main"
      statusItems={[{ label: "当前状态", tone: "danger", value: missing ? "内容不可用" : "页面暂时无法打开" }]}
      statusTestId="route-error-status"
      testId="route-error-page"
      title={missing ? "找不到这项内容" : "暂时无法打开页面"}
      tone="danger"
    />
  );
}
