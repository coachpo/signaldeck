import { ModelUsagePanel } from "./model-usage-panel";
import { connectionName } from "./task-labels";
import { Link } from "react-router";
import { useState } from "react";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { Field, FieldGroup } from "@/components/shared/form-field";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { useDisplayMode } from "@/hooks/use-display-mode";
import { usePlugins, useResources } from "@/hooks/use-workflow-platform";
import { RequestError } from "./feedback";
import { TaskConnections } from "./task-connections";
import { safePluginPageUrl } from "./plugin-links";

export function SettingsPage() {
  const { expert, setExpert, timeZone, setTimeZone } = useDisplayMode();
  const [zone, setZone] = useState(timeZone);
  const [zoneError, setZoneError] = useState("");
  const plugins = usePlugins();
  const resources = useResources();
  function saveZone() {
    try {
      new Intl.DateTimeFormat("zh-CN", { timeZone: zone }).format();
      setTimeZone(zone);
      setZoneError("");
    } catch {
      setZoneError("请选择有效时区，例如 Asia/Shanghai。");
    }
  }
  return (
    <InventoryPageShell
      pageContext={{ title: "设置", description: "显示偏好与已连接服务" }}
    >
      <div className="flex flex-col gap-4">
        <Card>
          <CardHeader>
            <CardTitle>显示偏好</CardTitle>
            <CardDescription>
              模式切换保留当前输入。已保存的自动执行时区保持不变。
            </CardDescription>
          </CardHeader>
          <CardContent>
            <FieldGroup>
              <Field label="工作模式">
                <label className="flex items-center gap-2">
                  <Switch
                    aria-label="在设置中开启专家模式"
                    checked={expert}
                    onCheckedChange={setExpert}
                  />
                  专家模式
                </label>
              </Field>
              <Field label="外观">
                <ThemeToggle />
              </Field>
              <Field
                label="新安排的默认时区"
                invalid={!!zoneError}
                description={zoneError || `当前偏好：${timeZone}`}
              >
                <Input
                  aria-label="默认时区"
                  aria-invalid={!!zoneError}
                  list="display-timezones"
                  value={zone}
                  onChange={(event) => setZone(event.target.value)}
                />
                <datalist id="display-timezones">
                  {Intl.supportedValuesOf("timeZone").map((value) => (
                    <option key={value} value={value} />
                  ))}
                  <option value="UTC" />
                </datalist>
                <Button variant="outline" onClick={saveZone}>
                  保存时区偏好
                </Button>
              </Field>
            </FieldGroup>
          </CardContent>
        </Card>
        <ModelUsagePanel />
        <Card>
          <CardHeader>
            <CardTitle>已连接服务</CardTitle>
            <CardDescription>
              配置存在不代表服务在线；最近调用记录反映实际观测。
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-col gap-3">
            <RequestError
              error={plugins.error || resources.error}
              retry={() => {
                void plugins.refetch();
                void resources.refetch();
              }}
            />
            {plugins.data?.items.map((plugin) => {
              const url = safePluginPageUrl(plugin.release.pageUrl);
              return (
                <div
                  key={plugin.pluginId}
                  className="flex flex-wrap items-center justify-between gap-2 border-b border-ui-separator py-2"
                >
                  <div>
                    <p>
                      {connectionName(plugin.pluginId, plugin.pluginId)} ·{" "}
                      {plugin.enabled ? "已启用" : "未启用"}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {plugin.health.observedAt
                        ? `最近调用：${plugin.health.status} · ${plugin.health.observedAt}`
                        : "尚无调用观测"}
                    </p>
                  </div>
                  {plugin.enabled && url && (
                    <Button asChild variant="outline">
                      <a href={url} target="_blank" rel="noopener noreferrer">
                        打开服务
                      </a>
                    </Button>
                  )}
                </div>
              );
            })}
            {plugins.data?.items.length === 0 && (
              <p>还没有登记服务。选择任务后可查看所需连接。</p>
            )}
            {resources.data && resources.data.items.length > 0 && (
              <TaskConnections
                requirements={resources.data.items.map((resource) => ({
                  id: resource.resourceId,
                  kind: resource.kind,
                  name:
                    typeof resource.config.name === "string"
                      ? resource.config.name
                      : resource.kind === "model"
                        ? "模型服务"
                        : "工具服务",
                  configured: true,
                  hasCredentials: resource.hasCredentials,
                  config: resource.config,
                  observation: resource.modelObservation?.status ?? "not_observed",
                  modelObservation: resource.modelObservation,
                  issue: null,
                }))}
                onSaved={() => {
                  void resources.refetch();
                }}
              />
            )}
            <Button asChild variant="outline">
              <Link to="/">选择任务并检查连接</Link>
            </Button>
            {expert && (
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline">
                  <Link to="/resources">完整资源配置</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link to="/plugins">插件发布与诊断</Link>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      </div>
    </InventoryPageShell>
  );
}
