import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { queryKeys } from "@/lib/query-keys";
import { workflowPlatformApi } from "@/lib/api/workflow-platform";
import type { ConfirmedContent } from "@/pages/platform/result-delivery";

export function useResultArtifactSelection() {
  const client = useQueryClient();
  const [loaded, setLoaded] = useState<Record<string, string>>({});
  const [pending, setPending] = useState<string[]>([]);
  const [errors, setErrors] = useState<Record<string, string>>({});
  async function read(item: ConfirmedContent) {
    if (!item.artifact) return;
    const artifact = item.artifact;
    setPending((ids) => [...ids, item.id]);
    setErrors((errors) => ({ ...errors, [item.id]: "" }));
    try {
      const text = await client.fetchQuery({
        queryKey: queryKeys.platform.artifacts.detail(artifact.digest),
        queryFn: () => workflowPlatformApi.artifact(artifact.digest), staleTime: Infinity,
      });
      setLoaded((values) => ({ ...values, [item.id]: text }));
    } catch {
      setErrors((errors) => ({ ...errors, [item.id]: "附件读取失败。请重试读取或取消选择。" }));
    } finally {
      setPending((ids) => ids.filter((id) => id !== item.id));
    }
  }
  return { loaded, pending, errors, read };
}
