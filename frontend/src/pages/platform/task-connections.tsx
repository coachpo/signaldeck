import { connectionName } from "./task-labels";
import { useState } from "react";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { TextField, ChoiceField } from "@/components/shared/form-field";
import { usePlatformMutations } from "@/hooks/use-workflow-platform";
import { useConnectionPresets } from "@/hooks/use-task-experience";
import { SafeSettings } from "./task-preparation";
import { RequestError } from "./feedback";
import type {
  ConnectionPreset,
  Requirement,
} from "@/lib/types/task-experience";

export function TaskConnections({
  requirements,
  onSaved,
}: {
  requirements: Requirement[];
  onSaved: () => void;
}) {
  const presets = useConnectionPresets();
  return (
    <section className="flex flex-col gap-3" aria-label="就地连接">
      <h2 className="font-medium">连接与保存位置</h2>
      <p className="text-sm text-muted-foreground">
        选择部署方提供的服务并确认业务范围；配置声明不代表当前在线。留空保留已有凭据，密钥不会保存在浏览器中。
      </p>
      <RequestError
        error={presets.error}
        retry={() => void presets.refetch()}
      />
      {requirements
        .filter((r) => r.kind !== "plugin")
        .map((r) => (
          <ConnectionEditor
            key={r.id}
            requirement={r}
            presets={
              presets.data?.items.filter(
                (p) => p.resourceId === r.id && p.kind === r.kind,
              ) ?? []
            }
            onSaved={onSaved}
          />
        ))}
      {requirements
        .filter((r) => r.kind === "plugin" && !r.configured)
        .map((r) => (
          <div key={r.id} className="flex flex-col gap-2">
            <p>
              {connectionName(r.name, r.id)}{" "}
              尚未部署或启用，需要在服务所在环境启动后登记发布信息。
            </p>
            <Button variant="outline" asChild>
              <Link to="/plugins">查看服务部署与发布设置</Link>
            </Button>
          </div>
        ))}
    </section>
  );
}
function ConnectionEditor({
  requirement,
  presets,
  onSaved,
}: {
  requirement: Requirement;
  presets: ConnectionPreset[];
  onSaved: () => void;
}) {
  const { saveResource } = usePlatformMutations();
  const [selected, setSelected] = useState("");
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [confirmed, setConfirmed] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [saved, setSaved] = useState(false);
  const preset = presets.find((p) => p.id === selected);
  const config =
    preset?.config ?? (requirement.configured ? requirement.config : null);
  const fields =
    preset?.credentialFields ??
    (requirement.kind === "model" && requirement.configured
      ? [{ key: "apiKey", label: "服务密钥", required: false }]
      : []);
  async function save() {
    if (requirement.kind === "plugin" || !config || !confirmed) return;
    const entered = Object.fromEntries(
      Object.entries(credentials).filter(([, value]) => value !== ""),
    );
    try {
      await saveResource.mutateAsync({
        resourceId: requirement.id,
        kind: requirement.kind,
        config,
        ...(Object.keys(entered).length ? { credentials: entered } : {}),
      });
      setCredentials({});
      setSaved(true);
      onSaved();
    } catch (e) {
      setError(e);
    }
  }
  return (
    <details className="rounded-md border border-ui-separator p-3">
      <summary className="cursor-pointer font-medium">
        {connectionName(requirement.name, requirement.id)} ·{" "}
        {requirement.configured ? "管理连接" : "补齐连接"}
      </summary>
      <div className="flex flex-col gap-3 pt-3">
        <RequestError error={error} />
        {presets.length > 0 && (
          <ChoiceField
            label="部署方提供的服务"
            value={selected}
            options={[
              ...(requirement.configured
                ? [{ value: "current", label: "保留当前连接" }]
                : []),
              ...presets.map((p) => ({ value: p.id, label: p.name })),
            ]}
            onChange={(value) => {
              setSelected(value);
              setCredentials({});
              setConfirmed(false);
              setSaved(false);
            }}
          />
        )}
        {preset?.description && (
          <p className="text-sm text-muted-foreground">{preset.description}</p>
        )}
        {config ? (
          <>
            <SafeSettings value={config} />
            {fields.map((field) => (
              <TextField
                key={field.key}
                label={field.label}
                type="password"
                value={credentials[field.key] ?? ""}
                onChange={(value) =>
                  setCredentials({ ...credentials, [field.key]: value })
                }
              />
            ))}
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              确认使用以上服务、账户、业务范围及保存位置
            </label>
            <Button
              variant="outline"
              onClick={() => void save()}
              disabled={
                saveResource.isPending ||
                !confirmed ||
                fields.some(
                  (field) =>
                    field.required &&
                    !credentials[field.key] &&
                    !requirement.hasCredentials,
                )
              }
            >
              保存连接
            </Button>
            {saved && (
              <p role="status">
                已保存。密钥输入已清空，连接配置已重新核对；实际连通性尚未观测。
              </p>
            )}
          </>
        ) : (
          <>
            <p className="text-sm">
              没有适用于此任务的部署方服务预设。需要先部署服务并配置连接预设；返回后输入仍会保留。
            </p>
            <Button variant="outline" asChild>
              <Link to="/resources">查看高级服务配置</Link>
            </Button>
          </>
        )}
      </div>
    </details>
  );
}
