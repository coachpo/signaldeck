import { useCallback, useEffect, useRef, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router";
import { useTheme } from "@/components/theme";
import { Button } from "@/components/ui/button";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import { useDisplayMode } from "@/hooks/use-display-mode";
import { usePluginPages } from "@/hooks/use-plugin-pages";
import type { PluginPage } from "@/lib/api/plugin-pages";
import { localPath, ownedPluginUrl, PLUGIN_UI_PROTOCOL, pluginRoute } from "./navigation";

const EMPTY_PAGES: PluginPage[] = [];

type Session = { page: PluginPage; returnTo?: string };

/** This layer stays mounted beside the outlet: a route change never destroys plugin memory. */
export function PluginHost() {
  const location = useLocation();
  const navigate = useNavigate();
  const catalog = usePluginPages();
  const pages = catalog.data ?? EMPTY_PAGES;
  const route = pluginRoute(`${location.pathname}${location.search}${location.hash}`);
  const [sessions, setSessions] = useState<Session[]>([]);
  const lastPaths = useRef(new Map<string, string>());
  useEffect(() => {
    const currentRoute = pluginRoute(`${location.pathname}${location.search}${location.hash}`);
    if (currentRoute) lastPaths.current.set(currentRoute.mountKey, `${location.pathname}${location.search}${location.hash}`);
  }, [location]);
  const current = route && sessions.find((session) => session.page.mountKey === route.mountKey);
  const page = route && pages.find((entry) => entry.mountKey === route.mountKey);
  if (route && page && !current) {
    const state = location.state as { pluginReturnTo?: unknown } | null;
    setSessions([...sessions, { page, returnTo: localPath(state?.pluginReturnTo) ? state.pluginReturnTo : undefined }]);
  }

  useEffect(() => {
    const follow = (event: MouseEvent) => {
      if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      const link = event.target instanceof Element ? event.target.closest("a[href]") : null;
      if (!(link instanceof HTMLAnchorElement) || link.hasAttribute("download") || (link.target && link.target !== "_self")) return;
      const path = ownedPluginUrl(link.href);
      if (!path) return;
      const target = pluginRoute(path);
      const destination = link.dataset.pluginResume === "true" && target ? lastPaths.current.get(target.mountKey) ?? path : path;
      event.preventDefault();
      navigate(destination, { state: { pluginReturnTo: location.pathname.startsWith("/runs/") ? `${location.pathname}${location.search}${location.hash}` : undefined } });
    };
    document.addEventListener("click", follow, true);
    return () => document.removeEventListener("click", follow, true);
  }, [navigate, location]);

  return <div hidden={!route} className="h-full min-h-0">
    {route && !current && !page ? <InventoryStatePanel title={catalog.isPending ? "正在打开页面" : "页面暂时无法打开"} description={catalog.isPending ? "正在读取可用入口。" : "请重试，或返回查看已保存的结果。"} action={<><Button onClick={() => void catalog.refetch()}>重试</Button><Button asChild variant="outline"><Link to="/runs">返回结果</Link></Button></>} /> : null}
    {sessions.map((session) => <PluginFrame key={session.page.mountKey} session={session} active={route?.mountKey === session.page.mountKey} path={route?.mountKey === session.page.mountKey ? route.path : undefined} returnTo={(location.state as { pluginReturnTo?: string } | null)?.pluginReturnTo} />)}
  </div>;
}

function PluginFrame({ session, active, path, returnTo }: { session: Session; active: boolean; path?: string; returnTo?: string }) {
  const frame = useRef<HTMLIFrameElement>(null);
  const navigate = useNavigate();
  const { theme } = useTheme();
  const { expert } = useDisplayMode();
  const [readyGeneration, setReadyGeneration] = useState(0);
  const ready = readyGeneration > 0;
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [status, setStatus] = useState({ dirty: false, busy: false });
  const [returnPath, setReturnPath] = useState(session.returnTo);
  if (active && localPath(returnTo) && returnTo !== returnPath) setReturnPath(returnTo);
  const initial = new URL(`/_plugins/${session.page.mountKey}/`, window.location.origin);
  initial.searchParams.set("embedded", "1");
  const post = useCallback((message: Record<string, unknown>) => frame.current?.contentWindow?.postMessage({ protocol: PLUGIN_UI_PROTOCOL, ...message }, window.location.origin), []);

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.origin !== window.location.origin || event.source !== frame.current?.contentWindow || !event.data || typeof event.data !== "object" || Array.isArray(event.data)) return;
      const data = event.data as Record<string, unknown>;
      if (data.protocol !== PLUGIN_UI_PROTOCOL) return;
      if (data.type === "ready" && Object.keys(data).every((key) => ["protocol", "type"].includes(key))) {
        setReadyGeneration((generation) => generation + 1); setFailed(false);
      } else if (data.type === "state" && Object.keys(data).every((key) => ["protocol", "type", "dirty", "busy"].includes(key)) && typeof data.dirty === "boolean" && typeof data.busy === "boolean") {
        setStatus({ dirty: data.dirty, busy: data.busy });
      } else if (data.type === "navigate" && active && Object.keys(data).every((key) => ["protocol", "type", "path", "replace", "target"].includes(key)) && localPath(data.path) && (data.replace === undefined || typeof data.replace === "boolean") && (data.target === undefined || data.target === "platform")) {
        const destination = data.target === "platform" ? data.path : `/apps/${session.page.mountKey}${data.path}`;
        if (data.target === "platform" && destination !== returnPath) return;
        navigate(destination, { replace: data.replace === true, state: { pluginReturnTo: returnPath } });
      }
    };
    window.addEventListener("message", receive);
    return () => window.removeEventListener("message", receive);
  }, [active, navigate, returnPath, session.page.mountKey]);

  useEffect(() => {
    if (ready) post({ type: "preferences", theme, expertMode: expert, ...(returnPath ? { returnTo: returnPath } : {}) });
  }, [ready, readyGeneration, theme, expert, returnPath, post]);
  useEffect(() => {
    if (ready && path) post({ type: "location", path });
  }, [path, ready, readyGeneration, post]);
  useEffect(() => {
    if (ready) return;
    const timeout = window.setTimeout(() => setFailed(true), 15_000);
    return () => window.clearTimeout(timeout);
  }, [ready, attempt]);
  useEffect(() => {
    const warn = (event: BeforeUnloadEvent) => {
      if (status.dirty || status.busy) { event.preventDefault(); event.returnValue = ""; }
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [status]);

  return <section hidden={!active} className="flex h-full min-h-0 flex-col" aria-label={session.page.title}>
    {returnPath ? <div className="border-b border-border px-4 py-2"><Link className="text-sm underline" to={returnPath}>返回来源结果</Link></div> : null}
    {!ready && !failed ? <InventoryStatePanel title={<span role="status">正在打开页面</span>} description="正在连接服务，请稍候。" /> : null}
    {failed ? <InventoryStatePanel title="页面暂时无法打开" description="服务可能暂时不可用。已保存的执行结果仍可查看。" action={<><Button onClick={() => { if (status.dirty || status.busy) return; setFailed(false); setReadyGeneration(0); setAttempt((value) => value + 1); }} disabled={status.dirty || status.busy}>重试</Button><Button variant="outline" asChild><Link to={returnPath || "/runs"}>返回结果</Link></Button></>} /> : null}
    <iframe key={attempt} ref={frame} title={session.page.title} src={initial.href} onError={() => setFailed(true)} className="min-h-0 w-full flex-1 border-0" hidden={!ready || failed} />
  </section>;
}

export function PluginRoute() { return null; }
