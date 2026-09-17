import type { DataRouter } from "react-router";
import { hasRetainedWork } from "./retained-work";

// Vite reports lazy pages that fail to import, e.g. files replaced by a
// restart or redeploy. The router and the browser module map keep that failure
// for the whole document, so only a new document recovers. A reloaded document
// that fails while loading itself keeps the route error instead of looping.
export function watchChunkLoadFailures(router: Pick<DataRouter, "state" | "subscribe">, target: Window = window) {
  let waiting = false;
  const reload = () => {
    waiting = false;
    if (!hasRetainedWork()) target.location.reload();
  };
  target.addEventListener("vite:preloadError", () => {
    const [navigation] = target.performance.getEntriesByType("navigation") as PerformanceNavigationTiming[];
    if (waiting || (!router.state.initialized && (navigation?.type ?? "reload") === "reload")) return;
    // Reload once the router has settled on the page being opened, so the new document opens that page.
    if (router.state.navigation.state === "idle") return reload();
    waiting = true;
    const unsubscribe = router.subscribe((state) => {
      if (state.navigation.state !== "idle") return;
      unsubscribe();
      reload();
    });
  });
}
