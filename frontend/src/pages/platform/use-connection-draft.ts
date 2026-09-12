import { useState } from "react";
import { useUnsavedWork } from "@/hooks/use-unsaved-work";
import type { JsonObject } from "@/lib/types/workflow-platform";

type Draft = { config: JsonObject; credentials: Record<string, string> };
const drafts = new Map<string, Draft>();
export function useConnectionDraft(key: string, initial: JsonObject) {
  const [draft, setState] = useState<Draft>(() => drafts.get(key) ?? { config: initial, credentials: {} });
  const dirty = drafts.has(key);
  useUnsavedWork(dirty);
  function update(next: Draft) { drafts.set(key, next); setState(next); }
  function saved(config: JsonObject) { drafts.delete(key); setState({ config, credentials: {} }); }
  return { ...draft, dirty, update, saved };
}
