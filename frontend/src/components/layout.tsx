import {
  Briefcase,
  ClipboardList,
  Database,
  FileText,
  LayoutDashboard,
  Link2,
  PlayCircle,
  Puzzle,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { Link, NavLink, Outlet, useLocation, useMatches } from "react-router";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "./ui/breadcrumb";
import { useDisplayMode } from "@/hooks/use-display-mode";
import { Switch } from "./ui/switch";
import { ThemeToggle } from "./theme-toggle";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "./ui/sidebar";
import { useSidebar } from "./ui/sidebar-context";

type RouteArchetype =
  | "dashboard"
  | "inventory"
  | "detail"
  | "editor"
  | "console"
  | "systemState"
  | "unknown";
type RouteShellMode = "scroll" | "fullHeight";
export type RouteWidthMode = "wide" | "full" | "compact" | "readable";
export type RouteNavGroup = "Agent Platform" | "System";
type RouteNavIconName =
  | "Briefcase"
  | "ClipboardList"
  | "Database"
  | "FileText"
  | "LayoutDashboard"
  | "Link2"
  | "PlayCircle"
  | "Puzzle"
  | "Workflow";
type RouteStateVariant =
  | "ready"
  | "loading"
  | "error"
  | "empty"
  | "filteredEmpty"
  | "unauthorized"
  | "notFound"
  | "creating"
  | "editing"
  | "saving"
  | "importing"
  | "validating"
  | "launching"
  | "polling";
export type RouteHandle = {
  archetype: RouteArchetype;
  breadcrumb: {
    parent?: {
      href: `/${string}`;
      title: string;
    };
    title: string;
  };
  nav: {
    group: RouteNavGroup;
    iconName: RouteNavIconName;
    label: string;
    path?: `/${string}`;
    sidebar: boolean;
    testId: string;
  };
  owner:
    | { kind: "platform" }
    | { kind: "system" }
    | {
        extensionKey: string;
        extensionLabel: string;
        kind: "extension";
      }
    | { kind: "unknown" };
  pattern: `/${string}` | "*";
  shellMode: RouteShellMode;
  stateVariants: readonly RouteStateVariant[];
  testId: string;
  widthMode: RouteWidthMode;
};
type RouteNavGroupHandle = {
  items: readonly RouteHandle[];
  label: RouteNavGroup;
};
export type RootRouteHandle = {
  sidebarGroups: readonly RouteNavGroupHandle[];
};

type NavItem = {
  icon: LucideIcon;
  label: string;
  testId: string;
  to: string;
};

const navIconByName: Record<RouteNavIconName, LucideIcon> = {
  Briefcase,
  ClipboardList,
  Database,
  FileText,
  LayoutDashboard,
  Link2,
  PlayCircle,
  Puzzle,
  Workflow,
};

function isRouteHandle(handle: unknown): handle is RouteHandle {
  return (
    typeof handle === "object" &&
    handle !== null &&
    "breadcrumb" in handle &&
    "shellMode" in handle &&
    "testId" in handle
  );
}

function isRootRouteHandle(handle: unknown): handle is RootRouteHandle {
  return (
    typeof handle === "object" && handle !== null && "sidebarGroups" in handle
  );
}

function activeRouteHandle(
  matches: readonly { handle: unknown }[],
): RouteHandle {
  for (let index = matches.length - 1; index >= 0; index -= 1) {
    const handle = matches[index]?.handle;

    if (isRouteHandle(handle)) {
      return handle;
    }
  }

  throw new Error("Current route is missing route handle metadata.");
}

function rootRouteHandle(
  matches: readonly { handle: unknown }[],
): RootRouteHandle {
  const rootHandle = matches.find((match) => isRootRouteHandle(match.handle));

  if (!rootHandle || !isRootRouteHandle(rootHandle.handle)) {
    throw new Error("Root route is missing sidebar handle metadata.");
  }

  return rootHandle.handle;
}

function assembleNavGroups(sidebarGroups: readonly RouteNavGroupHandle[]) {
  return sidebarGroups.map((group) => ({
    items: group.items.map((metadata) => {
      if (!metadata.nav.path) {
        throw new Error(
          `Sidebar route metadata is missing a nav path: ${metadata.pattern}`,
        );
      }

      return {
        icon: navIconByName[metadata.nav.iconName],
        label: metadata.nav.label,
        testId: metadata.nav.testId,
        to: metadata.nav.path,
      };
    }),
    label: group.label,
  }));
}

function isNavItemActive(pathname: string, item: NavItem) {
  return item.to === "/"
    ? pathname === "/" ||
        pathname === "/tasks" ||
        pathname.startsWith("/tasks/") ||
        pathname === "/scheduled-tasks" ||
        pathname.startsWith("/scheduled-tasks/")
    : pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function AppSidebar() {
  const location = useLocation();
  const matches = useMatches();
  const { expert } = useDisplayMode();
  const navGroups = assembleNavGroups(
    rootRouteHandle(matches).sidebarGroups,
  ).map((group) => ({
    ...group,
    items: group.items.filter(
      (item) =>
        item.to !== "/settings" &&
        item.to !== "/scheduled-tasks" &&
        (expert || item.to === "/" || item.to === "/runs" || item.to === "/attention"),
    ),
  }));
  const { isMobile, open, setOpenMobile } = useSidebar();
  const showExpandedContent = open || isMobile;

  return (
    <Sidebar variant="sidebar">
      <SidebarHeader className="h-[var(--ui-layout-header-height)] justify-center border-b border-sidebar-border/70 px-3 py-0">
        <div className="flex items-center gap-2">
          <div className="flex size-8 items-center justify-center rounded-md border border-sidebar-primary/15 bg-sidebar-primary/10 text-sidebar-primary shadow-ui-xs">
            <img
              alt=""
              aria-hidden="true"
              className="size-4 shrink-0"
              src="/favicon.svg"
            />
          </div>
          {showExpandedContent ? (
            <div className="min-w-0">
              <p className="text-sm font-semibold tracking-tight text-sidebar-foreground">
                SignalDeck
              </p>
            </div>
          ) : null}
        </div>
      </SidebarHeader>
      <SidebarContent>
        {navGroups.map((group) => (
          <SidebarGroup key={group.label}>
            {showExpandedContent ? (
              <SidebarGroupLabel>
                {expert ? "专家工作区" : "日常操作"}
              </SidebarGroupLabel>
            ) : null}
            <SidebarGroupContent>
              <SidebarMenu>
                {group.items.map((item) => (
                  <SidebarMenuItem key={item.to}>
                    <SidebarMenuButton
                      asChild
                      className={
                        !showExpandedContent ? "justify-center" : undefined
                      }
                      isActive={isNavItemActive(location.pathname, item)}
                      tooltip={!showExpandedContent ? item.label : undefined}
                    >
                      <NavLink
                        data-testid={item.testId}
                        end={item.to === "/"}
                        onClick={() => setOpenMobile(false)}
                        to={item.to}
                      >
                        <item.icon className="size-4 shrink-0" />
                        <span
                          className={
                            !showExpandedContent ? "sr-only" : undefined
                          }
                        >
                          {item.label}
                        </span>
                      </NavLink>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        ))}
      </SidebarContent>
      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              isActive={location.pathname === "/settings"}
            >
              <NavLink
                to="/settings"
                data-testid="nav-settings"
                onClick={() => setOpenMobile(false)}
              >
                <Database className="size-4" />
                <span>设置</span>
              </NavLink>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}

function routeWidthWrapperClassName(widthMode: RouteWidthMode) {
  switch (widthMode) {
    case "compact":
      return "min-h-full min-w-0 max-w-full [&>*]:mx-auto [&>*]:min-w-0 [&>*]:w-full [&>*]:max-w-[var(--ui-layout-compact)]";
    case "readable":
      return "min-h-full min-w-0 max-w-full [&>*]:mx-auto [&>*]:min-w-0 [&>*]:w-full [&>*]:max-w-[var(--ui-layout-readable)]";
    case "wide":
    default:
      return "min-h-full min-w-0 max-w-full [&>*]:min-w-0 [&>*]:w-full";
  }
}

export function Layout() {
  const matches = useMatches();
  const routeMetadata = activeRouteHandle(matches);
  const breadcrumbMetadata = routeMetadata.breadcrumb;
  const { expert, setExpert } = useDisplayMode();
  const usesFullHeightShell = routeMetadata.shellMode === "fullHeight";

  return (
    <SidebarProvider>
      <a
        className="sr-only z-[var(--ui-z-toast)] rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground shadow-ui-md focus:not-sr-only focus:fixed focus:left-4 focus:top-4"
        href="#app-main"
      >
        Skip to main content
      </a>
      <AppSidebar />
      <SidebarInset>
        <header className="sticky top-0 z-20 flex h-[var(--ui-layout-header-height)] items-center gap-2 border-b border-border/70 bg-ui-surface-chrome px-3 backdrop-blur-xl">
          <SidebarTrigger className="shrink-0" />
          <div className="min-w-0 flex-1">
            <Breadcrumb>
              <BreadcrumbList>
                {breadcrumbMetadata.parent ? (
                  <>
                    <BreadcrumbItem>
                      <BreadcrumbLink asChild>
                        <Link to={breadcrumbMetadata.parent.href}>
                          {breadcrumbMetadata.parent.title}
                        </Link>
                      </BreadcrumbLink>
                    </BreadcrumbItem>
                    <BreadcrumbSeparator />
                    <BreadcrumbItem>
                      <BreadcrumbPage>
                        {breadcrumbMetadata.title}
                      </BreadcrumbPage>
                    </BreadcrumbItem>
                  </>
                ) : (
                  <BreadcrumbItem>
                    <BreadcrumbPage>{breadcrumbMetadata.title}</BreadcrumbPage>
                  </BreadcrumbItem>
                )}
              </BreadcrumbList>
            </Breadcrumb>
          </div>
          <label className="flex shrink-0 items-center gap-2 text-sm">
            <Switch
              aria-label="专家模式"
              checked={expert}
              onCheckedChange={setExpert}
            />
            专家模式
          </label>
          <ThemeToggle />
        </header>

        <main
          id="app-main"
          className="min-h-0 min-w-0 flex-1 overflow-hidden"
          data-route-shell-mode={routeMetadata.shellMode}
          data-route-width-mode={
            usesFullHeightShell ? "full" : routeMetadata.widthMode
          }
          data-testid={routeMetadata.testId}
        >
          {usesFullHeightShell ? (
            <div className="h-full [&>*]:h-full [&>*]:w-full">
              <Outlet />
            </div>
          ) : (
            <div
              className="h-full min-w-0 overflow-x-hidden overflow-y-auto"
              data-slot="layout-scroll-viewport"
            >
              <div
                className={routeWidthWrapperClassName(routeMetadata.widthMode)}
              >
                <Outlet />
              </div>
            </div>
          )}
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
