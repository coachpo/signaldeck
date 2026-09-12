import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, it } from "vitest";
import { ThemeProvider } from "./theme-provider";
import { useTheme } from "./theme";
import { storeTheme, THEME_STORAGE_KEY } from "@/lib/display-preferences";

beforeEach(() => { storeTheme("light"); });
it("updates the visible theme when another tab changes its preference", () => {
  const { result } = renderHook(useTheme, { wrapper: ThemeProvider });
  expect(document.documentElement.classList.contains("dark")).toBe(false);
  act(() => {
    localStorage.setItem(THEME_STORAGE_KEY, "dark");
    window.dispatchEvent(new StorageEvent("storage", { key: THEME_STORAGE_KEY }));
  });
  expect(result.current.theme).toBe("dark");
  expect(document.documentElement.classList.contains("dark")).toBe(true);
});
