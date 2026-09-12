import { useEffect } from "react";

/** Keep refresh and tab-close from silently discarding work held in this page. */
export function useUnsavedWork(hasChanges: boolean) {
  useEffect(() => {
    if (!hasChanges) return;
    const protect = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", protect);
    return () => window.removeEventListener("beforeunload", protect);
  }, [hasChanges]);
}
