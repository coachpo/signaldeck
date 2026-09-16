import type { ReactNode } from "react";

import { cn } from "@/components/ui/utils";

export type WorkspacePageShellProps = {
  bodyAriaLabel?: string;
  bodyClassName?: string;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
  contextBar: ReactNode;
  contextBarClassName?: string;
  leftRail?: ReactNode;
  leftRailAriaLabel?: string;
  leftRailClassName?: string;
  testId?: string;
};

export function WorkspacePageShell({
  bodyAriaLabel = "页面内容",
  bodyClassName,
  children,
  className,
  contentClassName,
  contextBar,
  contextBarClassName,
  leftRail,
  leftRailAriaLabel = "Workspace navigation",
  leftRailClassName,
  testId = "workspace-page-shell",
}: WorkspacePageShellProps) {
  return (
    <div
      className={cn(
        "flex h-full min-h-0 min-w-0 flex-col overflow-hidden bg-ui-canvas font-sans",
        className,
      )}
      data-testid={testId}
    >
      <div
        className={cn(
          "sticky top-0 z-10 shrink-0 border-b border-border/70 bg-ui-surface-chrome p-4 backdrop-blur-xl",
          contextBarClassName,
        )}
        data-testid="workspace-page-shell-context"
        data-workspace-shell-region="context"
      >
        {contextBar}
      </div>

      <div
        className={cn(
          "flex min-h-0 min-w-0 flex-1 gap-3 overflow-hidden p-3 sm:p-4",
          leftRail ? "flex-col lg:flex-row" : "flex-col",
          contentClassName,
        )}
        data-testid="workspace-page-shell-content"
        data-workspace-shell-region="content"
      >
        {leftRail ? (
          <aside
            aria-label={leftRailAriaLabel}
            className={cn(
            "min-h-0 min-w-0 shrink-0 overflow-hidden lg:w-64",
            "rounded-xl border border-border/70 bg-card/80 shadow-ui-xs",
            leftRailClassName,
            )}
            data-testid="workspace-page-shell-left-rail"
            data-workspace-shell-region="left-rail"
          >
            {leftRail}
          </aside>
        ) : null}
        <section
          aria-label={bodyAriaLabel}
          className={cn(
            "flex min-h-0 min-w-0 flex-1 flex-col overflow-auto",
            bodyClassName,
          )}
          data-testid="workspace-page-shell-body"
          data-workspace-shell-region="body"
          tabIndex={0}
        >
          {children}
        </section>
      </div>
    </div>
  );
}
