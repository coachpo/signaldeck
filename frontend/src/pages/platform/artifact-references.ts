import type { Json, ArtifactRef } from "@/lib/types/workflow-platform";
export function findArtifacts(
  value: Json,
  path = "$",
): { path: string; ref: ArtifactRef }[] {
  if (!value || typeof value !== "object") return [];
  if (
    !Array.isArray(value) &&
    typeof value.digest === "string" &&
    /^sha256:[a-f0-9]{64}$/.test(value.digest) &&
    typeof value.sizeBytes === "number" &&
    typeof value.mediaType === "string"
  )
    return [{ path, ref: value as unknown as ArtifactRef }];
  return Object.entries(value).flatMap(([key, child]) =>
    findArtifacts(child, `${path}.${key}`),
  );
}
