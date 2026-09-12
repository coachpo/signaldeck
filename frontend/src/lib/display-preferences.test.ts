import { beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useDisplayMode } from "@/hooks/use-display-mode";
import { DISPLAY_STORAGE_KEY, getStoredExpert, getStoredTheme, readDisplayHandoff, storeExpert, storeTheme, withDisplayHandoff } from "./display-preferences";

beforeEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  sessionStorage.clear();
  window.history.replaceState(null, "", "/");
  storeTheme("system");
  storeExpert(false);
});
describe("display preference handoff", () => {
  it("round trips preferences while retaining business links and existing timezone", () => {
    localStorage.setItem(DISPLAY_STORAGE_KEY, JSON.stringify({ expert: false, timeZone: "Europe/Helsinki" }));
    const href = withDisplayHandoff("https://plugin.example/report?report=seven#summary", { theme: "dark", expert: true, platformOrigin: "https://platform.example" })!;
    const target = new URL(href);
    expect(target.searchParams.get("report")).toBe("seven");
    window.history.replaceState({ retained: true }, "", `/report${target.search}${target.hash}`);
    expect(readDisplayHandoff()).toBe("https://platform.example");
    expect(getStoredTheme()).toBe("dark");
    expect(getStoredExpert()).toBe(true);
    expect(JSON.parse(localStorage.getItem(DISPLAY_STORAGE_KEY)!)).toEqual({ expert: true, timeZone: "Europe/Helsinki" });
    expect(window.location.search).toBe("?report=seven");
    expect(window.location.hash).toBe("#summary");
    expect(window.history.state).toEqual({ retained: true });
  });
  it("retains only the validated platform origin across plugin navigation and refresh", () => {
    window.history.replaceState(null, "", "/?sdPlatform=https%3A%2F%2Fplatform.example");
    expect(readDisplayHandoff()).toBe("https://platform.example");
    window.history.replaceState(null, "", "/reports?report=seven");
    expect(readDisplayHandoff()).toBe("https://platform.example");
    window.history.replaceState(null, "", "/?sdPlatform=https%3A%2F%2Fbad.example%2Fsecret");
    expect(readDisplayHandoff()).toBeNull();
    expect(sessionStorage.getItem("signaldeck-platform-origin")).toBe("https://platform.example");
  });
  it("rejects credentials, non-http URLs and return locations containing business paths", () => {
    expect(withDisplayHandoff("javascript:alert(1)")).toBeNull();
    expect(withDisplayHandoff("https://user:secret@plugin.example")).toBeNull();
    window.history.replaceState(null, "", "/?sdTheme=invalid&sdExpert=yes&sdPlatform=https%3A%2F%2Fplatform.example%2Fsecret&keep=ok");
    expect(readDisplayHandoff()).toBeNull();
    expect(getStoredTheme()).toBe("system");
    expect(getStoredExpert()).toBe(false);
    expect(window.location.search).toBe("?keep=ok");
  });
  it("retains in-memory preferences if storage rejects writes", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("disabled"); });
    expect(() => { storeTheme("dark"); storeExpert(true); }).not.toThrow();
    expect(getStoredTheme()).toBe("dark");
    expect(getStoredExpert()).toBe(true);
  });
  it("updates mounted expert controls when another tab changes display preferences", () => {
    const { result } = renderHook(useDisplayMode);
    expect(result.current.expert).toBe(false);
    act(() => {
      localStorage.setItem(DISPLAY_STORAGE_KEY, JSON.stringify({ expert: true, timeZone: "UTC" }));
      window.dispatchEvent(new StorageEvent("storage", { key: DISPLAY_STORAGE_KEY }));
    });
    expect(result.current.expert).toBe(true);
    expect(result.current.timeZone).toBe("UTC");
  });
});
