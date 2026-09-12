import { AlertTriangle } from "lucide-react";
import { CanonicalErrorPage } from "@/components/shared/canonical-error-page";
import { Button } from "@/components/ui/button";

type ErrorBoundaryFallbackProps = {
  error: Error | null;
  onReset: () => void;
};

export function ErrorBoundaryFallback({ onReset }: ErrorBoundaryFallbackProps) {
  return (
    <CanonicalErrorPage
      action={<>
        <Button onClick={onReset}>重试打开</Button>
        <Button type="button" variant="outline" onClick={() => window.location.reload()}>重新加载</Button>
      </>}
      contentTestId="error-boundary-fallback-content"
      description="已保存的内容仍然保留，正在执行的任务会继续。"
      descriptionTestId="error-boundary-fallback-description"
      icon={<AlertTriangle className="size-4 text-destructive" />}
      meta={null}
      metaTestId="error-boundary-fallback-meta"
      panelDescription={<p className="w-full max-w-4xl break-words text-sm leading-6 text-muted-foreground" data-testid="error-boundary-fallback-error">请先重试打开。重新加载前，请留意尚未保存的输入；已保存草稿可以从任务首页恢复。</p>}
      panelTestId="error-boundary-fallback-panel"
      panelTitle="恢复页面"
      rootElement="div"
      statusItems={[{ label: "当前状态", tone: "danger", value: "页面暂时不可用" }]}
      statusTestId="error-boundary-fallback-status"
      testId="error-boundary-fallback-page"
      title="暂时无法显示页面"
      tone="danger"
    />
  );
}
