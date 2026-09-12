import { useState } from "react";
import { ChoiceField, Field, TextField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { ValueEditor } from "@/components/platform-authoring/generated-form/value-editor";
import type { JsonObject, Plugin } from "@/lib/types/workflow-platform";
import { pluginName } from "./connection-model";

export function ConnectionConfigFields({ kind, value, onChange, plugins = [], onValidityChange }: {
  kind: "model" | "tool"; value: JsonObject; onChange: (value: JsonObject) => void;
  plugins?: Plugin[]; onValidityChange?: (valid: boolean) => void;
}) {
  const set = (key: string, next: JsonObject[string]) => onChange({ ...value, [key]: next });
  const plugin = plugins.find((item) => item.pluginId === value.pluginId);
  const capabilities = value.providerCapabilities;
  const outputLimit = capabilities && typeof capabilities === "object" && !Array.isArray(capabilities)
    ? String(capabilities.outputTokenLimitParameter ?? "automatic") : "automatic";
  return <div className="flex min-w-0 flex-col gap-4">
    <TextField label="连接名称" value={String(value.name ?? "")} onChange={(next) => set("name", next)} />
    {kind === "model" ? <>
      <TextField label="服务地址" value={String(value.baseUrl ?? "")} onChange={(next) => set("baseUrl", next)} />
      <TextField label="模型名称" value={String(value.modelId ?? "")} onChange={(next) => set("modelId", next)} />
      <ChoiceField label="接入方式" value={String(value.apiStyle ?? "chat_completions")} options={[
        { value: "chat_completions", label: "通用聊天服务" }, { value: "responses", label: "OpenAI 新版服务" },
      ]} onChange={(next) => {
        const updated: JsonObject = { ...value, apiStyle: next };
        delete updated.providerCapabilities;
        onChange(updated);
      }} />
      <ChoiceField label="回答长度限制方式" value={outputLimit} options={[
        { value: "automatic", label: "使用服务默认方式" },
        ...(value.apiStyle === "responses" ? [{ value: "max_output_tokens", label: "限制完整回答长度" }] : [
          { value: "max_completion_tokens", label: "包含模型思考过程" }, { value: "max_tokens", label: "兼容传统聊天模型" },
        ]),
      ]} onChange={(next) => {
        const updated = { ...value };
        if (next === "automatic") delete updated.providerCapabilities;
        else updated.providerCapabilities = { outputTokenLimitParameter: next };
        onChange(updated);
      }} />
      <TextField label="最长等待时间（秒）" type="number" value={String(value.timeoutSeconds ?? 60)} onChange={(next) => set("timeoutSeconds", next === "" ? "" : Number(next))} />
    </> : <>
      <ChoiceField label="连接的服务" value={String(value.pluginId ?? "")} options={[
        ...plugins.map((item, index) => ({ value: item.pluginId, label: `${pluginName(item.release)}${plugins.filter((p) => pluginName(p.release) === pluginName(item.release)).length > 1 ? ` ${index + 1}` : ""}${item.enabled ? "" : "（尚未启用）"}` })),
        ...(value.pluginId && !plugin ? [{ value: String(value.pluginId), label: "原有服务（尚未添加）" }] : []),
      ]} onChange={(next) => onChange({ ...value, pluginId: next, ...(value.pluginId === next ? {} : { scope: {} }) })} />
      {!plugins.length && <p className="text-sm text-muted-foreground">先在扩展服务页面添加服务，再回来选择。已填写的内容会保留。</p>}
      <ValueEditor label="业务范围与保存位置" schema={plugin?.release.configSchema ?? { type: "object" }} value={value.scope ?? {}} onChange={(next) => set("scope", next)} onValidityChange={onValidityChange} />
      <TextField label="同时处理数量" type="number" value={String(value.maxConcurrentCalls ?? 4)} onChange={(next) => set("maxConcurrentCalls", next === "" ? "" : Number(next))} />
      <TextField label="每秒处理数量" type="number" value={String(value.requestsPerSecond ?? 10)} onChange={(next) => set("requestsPerSecond", next === "" ? "" : Number(next))} />
    </>}
  </div>;
}

export function ConnectionCredentials({ kind, values, onChange, fields = [], hasCredentials = false }: {
  kind: "model" | "tool"; values: Record<string, string>; onChange: (values: Record<string, string>) => void;
  fields?: { key: string; label: string; required: boolean }[]; hasCredentials?: boolean;
}) {
  const [custom, setCustom] = useState("");
  const declared = fields.length ? fields : kind === "model" ? [{ key: "apiKey", label: "服务密钥", required: false }] : [];
  const extra = Object.keys(values).filter((key) => !declared.some((field) => field.key === key));
  return <Field label="账户与访问凭据" description={hasCredentials ? "已保存密钥。留空保留原值；填写新值后保存即可更换。" : "需要登录的服务请填写密钥；不需要密钥的本地服务可留空。"}>
    {declared.map((field) => <TextField key={field.key} label={`${field.label}${field.required && !hasCredentials ? "（必填）" : ""}`} type="password" value={values[field.key] ?? ""} onChange={(next) => onChange({ ...values, [field.key]: next })} />)}
    {extra.map((key) => <div key={key} className="flex items-end gap-2">
      <div className="min-w-0 flex-1"><TextField label={key} type="password" value={values[key]} onChange={(next) => onChange({ ...values, [key]: next })} /></div>
      <Button variant="ghost" onClick={() => { const next = { ...values }; delete next[key]; onChange(next); }}>移除输入</Button>
    </div>)}
    <div className="flex items-end gap-2">
      <div className="min-w-0 flex-1"><TextField label="其他凭据名称" value={custom} onChange={setCustom} /></div>
      <Button variant="outline" disabled={!custom.trim() || [...extra, ...declared.map((f) => f.key)].includes(custom.trim())} onClick={() => { onChange({ ...values, [custom.trim()]: "" }); setCustom(""); }}>添加凭据</Button>
    </div>
  </Field>;
}
