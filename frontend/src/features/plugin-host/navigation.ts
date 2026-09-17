export const PLUGIN_UI_PROTOCOL = "signaldeck.pluginUi/1";
export function localPath(value: unknown): value is string {
  if (typeof value !== "string" || !value.startsWith("/") || value.startsWith("//") || (value.includes("\\") || [...value].some((char) => char.charCodeAt(0) < 32))) return false;
  try {
    const url = new URL(value, window.location.origin);
    return url.origin === window.location.origin && url.pathname === value.split(/[?#]/, 1)[0];
  } catch { return false; }
}
export function pluginRoute(value: string) {
  // Like React Router, read a location path such as "//" on this origin rather than as another host.
  const url = new URL(value.startsWith("//") ? window.location.origin + value : value, window.location.origin);
  const match = /^\/apps\/([a-zA-Z0-9_-]+)(\/.*)?$/.exec(url.pathname);
  return match ? { mountKey: match[1], path: `${match[2] || "/"}${url.search}${url.hash}` } : null;
}
export function ownedPluginUrl(value: string): string | null {
  try {
    const url = new URL(value, window.location.origin);
    if (url.origin !== window.location.origin || url.username || url.password) return null;
    const route = pluginRoute(url.href);
    return route
      ? `${url.pathname}${url.search}${url.hash}` : null;
  } catch { return null; }
}
