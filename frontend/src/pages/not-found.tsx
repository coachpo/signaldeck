import { Link } from "react-router";
import { ArrowLeft, SearchX } from "lucide-react";
import { CanonicalErrorPage } from "@/components/shared/canonical-error-page";
import { Button } from "@/components/ui/button";

export function NotFoundPage() {
  return (
    <CanonicalErrorPage
      action={<Button asChild size="sm"><Link to="/"><ArrowLeft data-icon="inline-start" />返回任务首页</Link></Button>}
      contentClassName="min-h-0 justify-start"
      contentTestId="not-found-content"
      description="链接可能已失效，或这项内容已经移除。"
      descriptionTestId="not-found-description"
      icon={<SearchX className="size-4" />}
      meta={null}
      metaTestId="not-found-meta"
      panelDescription="可以返回首页选择任务，或从结果页找回已完成的内容。"
      panelTestId="not-found-panel"
      panelTitle="继续使用 SignalDeck"
      rootClassName="min-h-[calc(100vh-3rem)]"
      statusItems={[{ label: "当前状态", tone: "warning", value: "页面不可用" }]}
      statusTestId="not-found-status"
      testId="not-found-page"
      title="找不到页面"
      tone="warning"
    />
  );
}
