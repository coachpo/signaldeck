import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { flushSync } from "react-dom";
import { ThemeProvider } from "@/components/theme-provider";
import { ThemeToggle } from "@/components/theme-toggle";
import { Switch } from "@/components/ui/switch";
import { SidebarInset, SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { PluginNavigation } from "./navigation";
import { getStoredExpert, readDisplayHandoff, storeExpert } from "@/lib/display-preferences";

type ShellOptions = {
  title: string;
  onExpertChange?: (expert: boolean) => void;
  expertDisabled?: () => boolean;
};

export function mountPluginShell(options: ShellOptions) {
  const platformOrigin = readDisplayHandoff();
  let expert = getStoredExpert();
  const content = document.querySelector("main");
  if (!content) throw new Error("Plugin workspace requires a main element");
  content.classList.add("plugin-content");
  content.id ||= "app-main";
  const header = document.querySelector("header");
  const host = document.createElement("div");
  if (header) header.replaceWith(host);
  else content.before(host);
  // Fieldset disabling does not cover links added by the shared navigation.
  host.addEventListener("click", (event) => {
    if (options.expertDisabled?.() && event.target instanceof Element && event.target.closest("a")) {
      event.preventDefault();
    }
  });
  const root = createRoot(host);
  const attachContent = (node: HTMLDivElement | null) => { if (node) node.append(content); };
  let updateView: (value: boolean) => void = () => {};
  const setExpert = (next: boolean) => {
    if (options.expertDisabled?.()) return;
    expert = next;
    storeExpert(next);
    updateView(next);
    options.onExpertChange?.(next);
  };
  function Shell() {
    const [value, setValue] = useState(expert);
    useEffect(() => {
      updateView = setValue;
      const sync = () => { const next = getStoredExpert(); if (next !== expert) setExpert(next); };
      window.addEventListener("storage", sync);
      return () => window.removeEventListener("storage", sync);
    }, []);
    return <ThemeProvider><SidebarProvider>
      <a href="#app-main" className="sr-only focus:not-sr-only">跳到正文</a>
      <PluginNavigation title={options.title} platformOrigin={platformOrigin} expert={value} />
      <SidebarInset>
        <header className="flex h-[var(--ui-layout-header-height)] shrink-0 items-center gap-2 border-b border-border/70 bg-ui-surface-chrome px-3">
          <SidebarTrigger /><span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{options.title}</span>
          {options.onExpertChange && <label className="flex shrink-0 items-center gap-2 text-sm"><Switch id="mode" aria-label="专家模式" checked={value} onCheckedChange={setExpert} />专家模式</label>}
          <ThemeToggle />
        </header>
        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto" ref={attachContent} />
      </SidebarInset>
    </SidebarProvider></ThemeProvider>;
  }
  flushSync(() => root.render(<Shell />));
  return { get expert() { return expert; }, setExpert };
}
