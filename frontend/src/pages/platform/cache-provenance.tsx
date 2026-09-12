import type { JsonObject } from "@/lib/types/workflow-platform";
import { ResultFreshness } from "./result-freshness";

export function CacheProvenance({ metadata }: { metadata: JsonObject }) {
  return metadata.cacheProvenance ? <ResultFreshness value={metadata.cacheProvenance} /> : null;
}
