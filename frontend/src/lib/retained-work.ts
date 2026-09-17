// Pages keep unsaved drafts and unconfirmed command identities in module
// memory after their editor closes; a document reload would drop them silently.
const sources = new Set<() => boolean>();

export function registerRetainedWork(hasWork: () => boolean) {
  sources.add(hasWork);
  return () => {
    sources.delete(hasWork);
  };
}

export function hasRetainedWork() {
  for (const hasWork of sources) if (hasWork()) return true;
  return false;
}
