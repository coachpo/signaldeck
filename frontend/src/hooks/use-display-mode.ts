import { useSyncExternalStore } from "react";

import { DISPLAY_CHANGE_EVENT, DISPLAY_STORAGE_KEY, getStoredDisplay, storeDisplay } from "@/lib/display-preferences";

type Preferences = { expert: boolean; timeZone: string };
const defaults: Preferences = {
  expert: false,
  timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
};
function readPreferences(): Preferences {
  const stored = getStoredDisplay();
  return { expert: stored.expert === true, timeZone: stored.timeZone ?? defaults.timeZone };
}
let preferences = readPreferences();
const listeners = new Set<() => void>();
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
function synchronize() {
  const next = readPreferences();
  if (next.expert === preferences.expert && next.timeZone === preferences.timeZone) return;
  preferences = next;
  listeners.forEach((listener) => listener());
}
window.addEventListener(DISPLAY_CHANGE_EVENT, synchronize);
window.addEventListener("storage", (event) => {
  if (event.key === DISPLAY_STORAGE_KEY || event.key === null) synchronize();
});
function update(value: Partial<Preferences>) { storeDisplay(value); }
export function useDisplayMode() {
  const value = useSyncExternalStore(
    subscribe,
    () => preferences,
    () => defaults,
  );
  return {
    ...value,
    setExpert: (expert: boolean) => update({ expert }),
    setTimeZone: (timeZone: string) => update({ timeZone }),
  };
}
