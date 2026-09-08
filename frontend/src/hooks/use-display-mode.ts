import { useSyncExternalStore } from "react";

const key = "signaldeck-display";
type Preferences = { expert: boolean; timeZone: string };
const defaults: Preferences = {
  expert: false,
  timeZone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
};
let preferences: Preferences = defaults;
try {
  const stored = JSON.parse(
    localStorage.getItem(key) || "null",
  ) as Partial<Preferences> | null;
  if (stored)
    preferences = {
      expert: stored.expert === true,
      timeZone:
        typeof stored.timeZone === "string"
          ? stored.timeZone
          : defaults.timeZone,
    };
} catch {
  /* Display preferences remain usable when storage is unavailable. */
}
const listeners = new Set<() => void>();
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
function update(value: Partial<Preferences>) {
  preferences = { ...preferences, ...value };
  try {
    localStorage.setItem(key, JSON.stringify(preferences));
  } catch {
    /* In-memory preference still applies. */
  }
  listeners.forEach((listener) => listener());
}
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
