export type DisplayTheme = "light" | "dark" | "system";
export const THEME_STORAGE_KEY = "signaldeck-theme";
export const DISPLAY_STORAGE_KEY = "signaldeck-display";
export const DISPLAY_CHANGE_EVENT = "signaldeck-display-change";
let themeWriteFailed = false;
let displayWriteFailed = false;
let fallbackTheme: DisplayTheme = "system";
let fallbackDisplay: { expert?: boolean; timeZone?: string } = {};

function validTheme(value: unknown): value is DisplayTheme {
  return value === "light" || value === "dark" || value === "system";
}
export function getStoredTheme(): DisplayTheme {
  if (themeWriteFailed) return fallbackTheme;
  try {
    const value = localStorage.getItem(THEME_STORAGE_KEY);
    return validTheme(value) ? value : "system";
  } catch { return fallbackTheme; }
}
export function getStoredDisplay() {
  if (displayWriteFailed) return fallbackDisplay;
  try {
    const value: unknown = JSON.parse(localStorage.getItem(DISPLAY_STORAGE_KEY) || "null");
    if (!value || typeof value !== "object" || Array.isArray(value)) return {};
    const stored = value as Record<string, unknown>;
    return { expert: stored.expert === true, timeZone: typeof stored.timeZone === "string" ? stored.timeZone : undefined };
  } catch { return fallbackDisplay; }
}
export function getStoredExpert(): boolean { return getStoredDisplay().expert === true; }
function notify() { window.dispatchEvent(new Event(DISPLAY_CHANGE_EVENT)); }
export function storeTheme(theme: DisplayTheme) {
  fallbackTheme = theme;
  try { localStorage.setItem(THEME_STORAGE_KEY, theme); themeWriteFailed = false; } catch { themeWriteFailed = true; }
  notify();
}
export function storeDisplay(value: { expert?: boolean; timeZone?: string }) {
  fallbackDisplay = { ...getStoredDisplay(), ...value };
  try { localStorage.setItem(DISPLAY_STORAGE_KEY, JSON.stringify(fallbackDisplay)); displayWriteFailed = false; } catch { displayWriteFailed = true; }
  notify();
}
export function storeExpert(expert: boolean) { storeDisplay({ expert }); }

function httpUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) && !url.username && !url.password ? url : null;
  } catch { return null; }
}
function platformOrigin(value: string): string | null {
  const url = httpUrl(value);
  return url && url.pathname === "/" && !url.search && !url.hash ? url.origin : null;
}
/** Only presentation preferences and a platform origin cross the plugin boundary. */
export function withDisplayHandoff(value: string, options: {
  theme?: DisplayTheme; expert?: boolean; platformOrigin?: string;
} = {}): string | null {
  const url = httpUrl(value);
  if (!url) return null;
  url.searchParams.set("sdTheme", options.theme ?? getStoredTheme());
  url.searchParams.set("sdExpert", String(options.expert ?? getStoredExpert()));
  const origin = platformOrigin(options.platformOrigin ?? window.location.origin);
  url.searchParams.delete("sdPlatform");
  if (origin) url.searchParams.set("sdPlatform", origin);
  return url.href;
}
/** Consume once before mounting a platform or independently hosted plugin. */
export function readDisplayHandoff(): string | null {
  const url = new URL(window.location.href);
  const theme = url.searchParams.get("sdTheme");
  const expert = url.searchParams.get("sdExpert");
  let platform = platformOrigin(url.searchParams.get("sdPlatform") ?? "");
  try {
    if (platform) sessionStorage.setItem("signaldeck-platform-origin", platform);
    else if (!url.searchParams.has("sdPlatform")) {
      platform = platformOrigin(sessionStorage.getItem("signaldeck-platform-origin") ?? "");
    }
  } catch { /* The current navigation remains usable without session storage. */ }
  if (validTheme(theme)) storeTheme(theme);
  if (expert === "true" || expert === "false") storeExpert(expert === "true");
  const keys = ["sdTheme", "sdExpert", "sdPlatform"];
  if (keys.some((key) => url.searchParams.has(key))) {
    keys.forEach((key) => url.searchParams.delete(key));
    window.history.replaceState(window.history.state, "", url.href);
  }
  return platform;
}
