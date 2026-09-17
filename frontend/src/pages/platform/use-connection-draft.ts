import { useState } from "react";
import { useUnsavedWork } from "@/hooks/use-unsaved-work";
import type { JsonObject } from "@/lib/types/workflow-platform";
import { registerRetainedWork } from "@/lib/retained-work";

type Draft = { config: JsonObject; credentials: Record<string, string> };
const drafts = new Map<string, Draft>();
registerRetainedWork(() => drafts.size > 0);
export function useConnectionDraft(key: string, initial: JsonObject) {
  const [draft, setState] = useState<Draft>(() => drafts.get(key) ?? { config: initial, credentials: {} });
  const dirty = drafts.has(key);
  useUnsavedWork(dirty);
  function update(next: Draft) { drafts.set(key, next); setState(next); }
  function saved(config: JsonObject) { drafts.delete(key); setState({ config, credentials: {} }); }
  return { ...draft, dirty, update, saved };
}
