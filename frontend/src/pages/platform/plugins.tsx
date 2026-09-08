import { safePluginPageUrl } from "./plugin-links";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { Field, FieldGroup } from "@/components/shared/form-field";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardDescription,
} from "@/components/ui/card";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import {
  usePlugins,
  usePlatformMutations,
} from "@/hooks/use-workflow-platform";
import { parseObject } from "@/lib/platform-authoring/package-source";
import type { PluginRelease } from "@/lib/types/workflow-platform";
import { PluginHealth } from "./plugin-health";
import { RequestError } from "./feedback";
import { CopyButton } from "@/components/shared/copy-button";

export function PluginsPage() {
  const query = usePlugins();
  const mutations = usePlatformMutations();
  const [release, setRelease] = useState("");
  const [error, setError] = useState<unknown>(null);
  async function register() {
    try {
      await mutations.savePlugin.mutateAsync({
        release: parseObject(release) as unknown as PluginRelease,
        enabled: false,
      });
      setRelease("");
      setError(null);
    } catch (e) {
      setError(e);
    }
  }
  return (
    <InventoryPageShell
      pageContext={{
        title: "Plugins",
        description: "Independent releases and their tool contracts",
      }}
    >
      <div className="flex flex-col gap-4">
        <RequestError
          error={query.error || error || mutations.enablePlugin.error}
          retry={() => void query.refetch()}
        />
        {query.data?.items.map((plugin) => {
          const pageUrl = safePluginPageUrl(plugin.release.pageUrl);
          return (
            <Card key={plugin.pluginId}>
              <CardHeader>
                <CardTitle>{plugin.pluginId}</CardTitle>
                <CardDescription>
                  {plugin.release.releaseId} · {plugin.release.protocolVersion}
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <code className="break-all text-xs">
                  {plugin.release.artifactDigest}
                </code>
                <div className="flex flex-wrap gap-2">
                  <CopyButton
                    value={plugin.pluginId}
                    text="复制插件 ID"
                    label={`复制插件 ID ${plugin.pluginId}`}
                  />
                  <CopyButton
                    value={plugin.release.releaseId}
                    text="复制发布 ID"
                    label={`复制发布 ID ${plugin.pluginId}`}
                  />
                  <ResourceStatusBadge
                    label={plugin.enabled ? "Enabled" : "Disabled"}
                  />
                  <Button
                    variant="outline"
                    disabled={mutations.enablePlugin.isPending}
                    onClick={() =>
                      mutations.enablePlugin.mutate({
                        id: plugin.pluginId,
                        enabled: !plugin.enabled,
                      })
                    }
                  >
                    {plugin.enabled ? "Disable" : "Enable"} {plugin.pluginId}
                  </Button>
                  {plugin.enabled && pageUrl && (
                    <Button asChild variant="outline">
                      <a
                        href={pageUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        Open {plugin.pluginId}
                      </a>
                    </Button>
                  )}
                </div>
                <PluginHealth health={plugin.health} />
                <details>
                  <summary className="cursor-pointer text-sm">
                    完整发布描述
                  </summary>
                  <pre className="overflow-auto text-xs">
                    {JSON.stringify(plugin.release, null, 2)}
                  </pre>
                </details>
                <details>
                  <summary className="cursor-pointer text-sm">
                    Tool contracts ({plugin.release.tools.length})
                  </summary>
                  <pre className="overflow-auto text-xs">
                    {JSON.stringify(plugin.release.tools, null, 2)}
                  </pre>
                </details>
              </CardContent>
            </Card>
          );
        })}
        <Card>
          <CardHeader>
            <CardTitle>Register release</CardTitle>
            <CardDescription>
              Register a pinned release manifest. Enable it when its independent
              service is ready.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <Field label="Plugin release JSON">
                <Textarea
                  aria-label="Plugin release JSON"
                  value={release}
                  onChange={(e) => setRelease(e.target.value)}
                  className="min-h-40 font-mono text-xs"
                />
              </Field>
              <Button
                disabled={!release || mutations.savePlugin.isPending}
                onClick={() => void register()}
              >
                Register plugin
              </Button>
            </FieldGroup>
          </CardContent>
        </Card>
      </div>
    </InventoryPageShell>
  );
}
