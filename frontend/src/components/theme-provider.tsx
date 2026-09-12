import { useCallback, useEffect, useState } from "react";

import { ThemeContext, type Theme } from "@/components/theme";

import { DISPLAY_CHANGE_EVENT, THEME_STORAGE_KEY, getStoredTheme, storeTheme } from "@/lib/display-preferences";

function getSystemTheme(): "light" | "dark" {
  if (typeof window === "undefined" || !window.matchMedia) {
    return "light";
  }

  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function applyTheme(theme: Theme) {
  if (typeof document === "undefined") {
    return;
  }

  const resolved = theme === "system" ? getSystemTheme() : theme;
  document.documentElement.classList.toggle("dark", resolved === "dark");
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getStoredTheme);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    storeTheme(next);
    applyTheme(next);
  }, []);

  useEffect(() => {
    const sync = () => setThemeState(getStoredTheme());
    const storage = (event: StorageEvent) => {
      if (event.key === THEME_STORAGE_KEY || event.key === null) sync();
    };
    window.addEventListener("storage", storage);
    window.addEventListener(DISPLAY_CHANGE_EVENT, sync);
    return () => {
      window.removeEventListener("storage", storage);
      window.removeEventListener(DISPLAY_CHANGE_EVENT, sync);
    };
  }, []);

  useEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    if (theme !== "system") return;
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    const handler = () => applyTheme("system");
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [theme]);

  return (
    <ThemeContext.Provider value={{ theme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  );
}
