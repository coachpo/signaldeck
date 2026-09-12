import { ClipboardList, FileText, Settings } from "lucide-react";
import brandMark from "../../public/favicon.svg?raw";
import { useTheme } from "@/components/theme";
import { Sidebar, SidebarContent, SidebarFooter, SidebarGroup, SidebarGroupLabel, SidebarHeader, SidebarMenu, SidebarMenuButton, SidebarMenuItem } from "@/components/ui/sidebar";
import { useSidebar } from "@/components/ui/sidebar-context";
import { withDisplayHandoff } from "@/lib/display-preferences";

export function PluginNavigation({ title, platformOrigin, expert }: { title: string; platformOrigin: string | null; expert: boolean }) {
  const { theme } = useTheme();
  const { open, isMobile } = useSidebar();
  const expanded = open || isMobile;
  const links = [["/", "任务", ClipboardList], ["/runs", "结果", FileText]] as const;
  const link = (path: string) => withDisplayHandoff(new URL(path, platformOrigin!).href, { theme, expert, platformOrigin: platformOrigin! }) ?? "#";
  return <Sidebar>
    <SidebarHeader className="h-[var(--ui-layout-header-height)] justify-center border-b border-sidebar-border/70 px-3 py-0">
      <div className="flex items-center gap-2"><div className="flex size-8 items-center justify-center rounded-md border border-sidebar-primary/15 bg-sidebar-primary/10 text-sidebar-primary shadow-ui-xs"><img alt="" aria-hidden="true" className="size-4 shrink-0" src={"data:image/svg+xml," + encodeURIComponent(brandMark)} /></div>{expanded && <strong className="text-sm">SignalDeck</strong>}</div>
    </SidebarHeader>
    <SidebarContent><SidebarGroup>
      {expanded && <SidebarGroupLabel>工作区</SidebarGroupLabel>}
      <SidebarMenu>
        {platformOrigin && links.map(([path, label, Icon]) => <SidebarMenuItem key={path}><SidebarMenuButton asChild tooltip={!expanded ? label : undefined}><a href={link(path)}><Icon /><span className={!expanded ? "sr-only" : undefined}>{label}</span></a></SidebarMenuButton></SidebarMenuItem>)}
        <SidebarMenuItem><SidebarMenuButton isActive aria-current="page" tooltip={!expanded ? title : undefined}><FileText /><span className={!expanded ? "sr-only" : undefined}>{title}</span></SidebarMenuButton></SidebarMenuItem>
      </SidebarMenu>
    </SidebarGroup></SidebarContent>
    {platformOrigin && <SidebarFooter><SidebarMenu><SidebarMenuItem><SidebarMenuButton asChild tooltip={!expanded ? "设置" : undefined}><a href={link("/settings")}><Settings /><span className={!expanded ? "sr-only" : undefined}>设置</span></a></SidebarMenuButton></SidebarMenuItem></SidebarMenu></SidebarFooter>}
  </Sidebar>;
}

