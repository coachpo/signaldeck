import { ModelUsagePanel } from "./model-usage-panel";
import { pluginName } from "./connection-model";
import { PluginHealth } from "./plugin-health";
import { Link } from "react-router";
import { useState } from "react";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { Field, FieldGroup, ChoiceField } from "@/components/shared/form-field";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { useDisplayMode } from "@/hooks/use-display-mode";
import { usePlugins, useResources } from "@/hooks/use-workflow-platform";
import { RequestError } from "./feedback";
import { TaskConnections } from "./task-connections";
import { usePluginNavigationUrl } from "./plugin-links";

export function SettingsPage() {
  const pluginNavigationUrl = usePluginNavigationUrl();
  const { expert, setExpert, timeZone, setTimeZone } = useDisplayMode();
  const [zone, setZone] = useState(timeZone);
  const [zoneError, setZoneError] = useState("");
  const [zoneSaved, setZoneSaved] = useState(false);
  const plugins = usePlugins();
  const resources = useResources();
  function saveZone() {
    try {
      new Intl.DateTimeFormat("zh-CN", { timeZone: zone }).format();
      setTimeZone(zone);
      setZoneError("");
      setZoneSaved(true);
    } catch {
      setZoneError("请选择有效的城市时区。");
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
                description={zoneError || "新建自动执行时使用这个时区。已经保存的安排保持原时区。"}
              >
                <ChoiceField
                  label="默认时区"
                  value={zone}
                  onChange={(value) => { setZone(value); setZoneSaved(false); }}
                  options={[...new Set(["UTC", timeZone, ...Intl.supportedValuesOf("timeZone")])].map((value) => ({ value, label: `${value.split("/").at(-1)?.replaceAll("_", " ")} · ${new Intl.DateTimeFormat("zh-CN", { timeZone: value, timeZoneName: "longGeneric" }).formatToParts().find((part) => part.type === "timeZoneName")?.value ?? value}` }))}
                />
                <Button variant="outline" onClick={saveZone}>
                  保存时区偏好
                </Button>
                {zoneSaved && <p role="status" className="text-sm">已保存时区偏好。</p>}
              </Field>
            </FieldGroup>
          </CardContent>
        </Card>
        <ModelUsagePanel />
        <Card>
          <CardHeader>
            <CardTitle>已连接服务</CardTitle>
            <CardDescription>
              最近使用记录帮助判断服务状态；尚未使用的连接需要通过任务执行确认。
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
              const url = pluginNavigationUrl(plugin.release.pageUrl);
              return (
                <div
                  key={plugin.pluginId}
                  className="flex flex-wrap items-center justify-between gap-2 border-b border-ui-separator py-2"
                >
                  <div>
                    <p>
                      {pluginName(plugin.release)} ·{" "}
                      {plugin.enabled ? "已启用" : "未启用"}
                    </p>
                    <PluginHealth health={plugin.health} />
                  </div>
                  {plugin.enabled && url && (
                    <Button asChild variant="outline">
                      <a href={url} rel="noopener noreferrer">
                        打开服务
                      </a>
                    </Button>
                  )}
                </div>
              );
            })}
            {plugins.data?.items.length === 0 && (
              <p>还没有添加扩展服务。选择任务后可查看所需连接。</p>
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
              <div className="flex flex-wrap gap-2">
                <Button asChild variant="outline">
                  <Link to="/resources">管理服务连接</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link to="/plugins">管理扩展服务</Link>
                </Button>
              </div>
          </CardContent>
        </Card>
      </div>
    </InventoryPageShell>
  );
}
