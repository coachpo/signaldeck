import { requestPlatform } from "@/lib/api-client";

export type PluginPage = {
  mountKey: string;
  pluginId: string;
  artifactDigest: string;
  title: string;
  pageUrl: string;
  enabled: boolean;
};
export async function getPluginPages(): Promise<PluginPage[]> {
  const pages = await requestPlatform<PluginPage[]>("/plugin-pages");
  return Array.isArray(pages) ? pages : [];
}
