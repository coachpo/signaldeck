import type { ComponentType } from "react";
import { createBrowserRouter } from "react-router";
import {
  Layout,
  type RootRouteHandle,
  type RouteHandle,
} from "./components/layout";
import { RouteErrorPage } from "./pages/route-error";
type PageModule = { Component: ComponentType };
type Definition = {
  path?: string;
  index?: boolean;
  handle: RouteHandle;
  lazy: () => Promise<PageModule>;
};
function route(
  path: string,
  title: string,
  iconName: RouteHandle["nav"]["iconName"],
  lazy: () => Promise<PageModule>,
  options: {
    parent?: { href: `/${string}`; title: string };
    fullHeight?: boolean;
    sidebar?: boolean;
    testId?: string;
  } = {},
): Definition {
  const navPath = options.parent?.href ?? `/${path}`;
  const testId = options.testId ?? path.replace(/[:/]/g, "-");
  return {
    ...(path ? { path } : { index: true }),
    lazy,
    handle: {
      archetype: options.fullHeight ? "editor" : "inventory",
      breadcrumb: { title, parent: options.parent },
      nav: {
        group: "Agent Platform",
        iconName,
        label: options.parent?.title ?? title,
        path: navPath,
        sidebar: options.sidebar ?? !options.parent,
        testId: `nav-${testId}`,
      },
      owner: { kind: "platform" },
      pattern: path ? `/${path}` : "/",
      shellMode: options.fullHeight ? "fullHeight" : "scroll",
      stateVariants: ["loading", "ready", "error", "empty"],
      testId: `route-${testId}`,
      widthMode: options.fullHeight ? "full" : "wide",
    },
  };
}
const packageParent = {
  href: "/workflow-packages",
  title: "Workflow Packages",
} as const;
const scheduleParent = {
  href: "/scheduled-tasks",
  title: "Scheduled Tasks",
} as const;
const children: Definition[] = [
  route(
    "",
    "Dashboard",
    "LayoutDashboard",
    async () => ({
      Component: (await import("./pages/platform/dashboard")).DashboardPage,
    }),
    { testId: "dashboard" },
  ),
  route("workflow-packages", "Workflow Packages", "Workflow", async () => ({
    Component: (await import("./pages/platform/package-list")).PackagesPage,
  })),
  route(
    "workflow-packages/new",
    "New Workflow Package",
    "Workflow",
    async () => ({
      Component: (await import("./pages/platform/packages")).PackageEditorPage,
    }),
    { parent: packageParent, fullHeight: true },
  ),
  route(
    "workflow-packages/:packageId",
    "Workflow Package",
    "Workflow",
    async () => ({
      Component: (await import("./pages/platform/packages")).PackageEditorPage,
    }),
    { parent: packageParent, fullHeight: true },
  ),
  route(
    "workflow-packages/:packageId/run",
    "Launch Workflow",
    "Workflow",
    async () => ({
      Component: (await import("./pages/platform/launch")).LaunchPage,
    }),
    { parent: packageParent, fullHeight: true },
  ),
  route("resources", "Resources", "Database", async () => ({
    Component: (await import("./pages/platform/resources")).ResourcesPage,
  })),
  route("plugins", "Plugins", "Puzzle", async () => ({
    Component: (await import("./pages/platform/plugins")).PluginsPage,
  })),
  route("scheduled-tasks", "Scheduled Tasks", "ClipboardList", async () => ({
    Component: (await import("./pages/platform/schedule-list")).SchedulesPage,
  })),
  route(
    "scheduled-tasks/new",
    "New Scheduled Task",
    "ClipboardList",
    async () => ({
      Component: (await import("./pages/platform/schedules")).SchedulePage,
    }),
    { parent: scheduleParent, fullHeight: true },
  ),
  route(
    "scheduled-tasks/:scheduleId",
    "Scheduled Task",
    "ClipboardList",
    async () => ({
      Component: (await import("./pages/platform/schedules")).SchedulePage,
    }),
    { parent: scheduleParent, fullHeight: true },
  ),
  route("runs", "Runs", "PlayCircle", async () => ({
    Component: (await import("./pages/platform/runs")).RunsPage,
  })),
  route(
    "runs/:runId",
    "Run Detail",
    "PlayCircle",
    async () => ({
      Component: (await import("./pages/platform/runs")).RunPage,
    }),
    { parent: { href: "/runs", title: "Runs" }, fullHeight: true },
  ),
  route(
    "*",
    "Page not found",
    "Puzzle",
    async () => ({
      Component: (await import("./pages/not-found")).NotFoundPage,
    }),
    { sidebar: false, testId: "unknown" },
  ),
];
const handle: RootRouteHandle = {
  sidebarGroups: [
    {
      label: "Agent Platform",
      items: children.map((r) => r.handle).filter((h) => h.nav.sidebar),
    },
  ],
};
export const router = createBrowserRouter([
  {
    path: "/",
    Component: Layout,
    ErrorBoundary: RouteErrorPage,
    handle,
    children,
  },
]);
