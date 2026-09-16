import { useQuery } from "@tanstack/react-query";
import { getPluginPages } from "@/lib/api/plugin-pages";
import { queryKeys } from "@/lib/query-keys";

export function usePluginPages() {
  return useQuery({ queryKey: queryKeys.platform.plugins.pages(), queryFn: getPluginPages, refetchInterval: 30_000 });
}
