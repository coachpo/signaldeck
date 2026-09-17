import type { DataRouter, RouterState } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { watchChunkLoadFailures } from "./chunk-recovery";
import { registerRetainedWork } from "./retained-work";

const disposers: (() => void)[] = [];
afterEach(() => disposers.splice(0).forEach((dispose) => dispose()));

function page({ navigationType, initialized = true, navigating = false }: { navigationType?: NavigationTimingType; initialized?: boolean; navigating?: boolean }) {
  const target = new EventTarget();
  const reload = vi.fn();
  Object.assign(target, {
    performance: { getEntriesByType: () => (navigationType ? [{ type: navigationType }] : []) },
    location: { reload },
  });
  const listeners = new Set<(state: RouterState) => void>();
  const router = {
    state: { initialized, navigation: { state: navigating ? "loading" : "idle" } },
    subscribe: (listener: (state: RouterState) => void) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
  watchChunkLoadFailures(router as unknown as DataRouter, target as unknown as Window);
  return {
    reload,
    listeners,
    fail: () => target.dispatchEvent(new Event("vite:preloadError", { cancelable: true })),
    settle: (state: string) => [...listeners].forEach((listener) => listener({ navigation: { state } } as RouterState)),
  };
}

it("opens a new document when a page from an earlier build or restart cannot load", () => {
  for (const initialized of [true, false]) {
    const { reload, fail } = page({ navigationType: "navigate", initialized });
    expect(fail()).toBe(true);
    expect(reload).toHaveBeenCalledOnce();
  }
});

it("reloads once after the router has settled on the page being opened", () => {
  const { reload, fail, settle, listeners } = page({ navigationType: "navigate", navigating: true });
  fail();
  fail();
  expect(reload).not.toHaveBeenCalled();
  settle("loading");
  expect(reload).not.toHaveBeenCalled();
  settle("idle");
  expect(reload).toHaveBeenCalledOnce();
  expect(listeners.size).toBe(0);
});

it("keeps the route error when a reloaded document cannot load its own page", () => {
  for (const navigationType of ["reload", undefined] as const) {
    const { reload, fail } = page({ navigationType, initialized: false });
    fail();
    expect(reload).not.toHaveBeenCalled();
  }
});

it("recovers again in a reloaded document after a later redeploy", () => {
  for (const navigationType of ["reload", undefined] as const) {
    const { reload, fail } = page({ navigationType });
    fail();
    expect(reload).toHaveBeenCalledOnce();
  }
});

it("keeps the route error instead of discarding drafts or unconfirmed requests held in memory", () => {
  let retained = true;
  disposers.push(registerRetainedWork(() => retained));
  const { reload, fail, settle } = page({ navigationType: "navigate", navigating: true });
  expect(fail()).toBe(true);
  settle("idle");
  expect(reload).not.toHaveBeenCalled();
  retained = false;
  fail();
  settle("idle");
  expect(reload).toHaveBeenCalledOnce();
});
