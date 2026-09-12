import { useSyncExternalStore } from "react";
import { DISPLAY_CHANGE_EVENT, DISPLAY_STORAGE_KEY, THEME_STORAGE_KEY, getStoredTheme, getStoredExpert, withDisplayHandoff } from "@/lib/display-preferences";

export function safePluginPageUrl(value?: string | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password
      ? url.href
      : null;
  } catch {
    return null;
  }
}

export function pluginNavigationUrl(value?: string | null): string | null {
  const safe = safePluginPageUrl(value);
  return safe ? withDisplayHandoff(safe) : null;
}

function subscribePreferences(listener: () => void) {
  const storage = (event: StorageEvent) => {
    if (event.key === null || event.key === DISPLAY_STORAGE_KEY || event.key === THEME_STORAGE_KEY) listener();
  };
  window.addEventListener(DISPLAY_CHANGE_EVENT, listener);
  window.addEventListener("storage", storage);
  return () => {
    window.removeEventListener(DISPLAY_CHANGE_EVENT, listener);
    window.removeEventListener("storage", storage);
  };
}
export function usePluginNavigationUrl() {
  useSyncExternalStore(subscribePreferences, () => `${getStoredTheme()}:${getStoredExpert()}`, () => "system:false");
  return pluginNavigationUrl;
}
