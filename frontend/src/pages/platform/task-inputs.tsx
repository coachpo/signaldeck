import { useId } from "react";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
import { isJsonObject } from "@/lib/platform-authoring/parameter-values";

const labels: Record<string, string> = {
  title: "标题",
  text: "原文",
  query: "查找已有笔记",
  summarize: "整理并总结原文",
  question: "想了解什么",
  symbols: "研究对象",
  includeRisk: "包含风险分析",
};
const examples: Record<string, string> = {
  title: "例如：本周产品访谈",
  text: "粘贴需要保存或整理的内容",
  query: "用于查找相关笔记的关键词，可留空",
  question: "例如：最近有哪些变化？请说明依据和缺失信息。",
  symbols: "例如：AAPL",
};
function taskFieldLabel(key: string) {
  return labels[key] ?? key;
}
export function TaskInputs({
  schema,
  value,
  onChange,
  errors = {},
}: {
  schema: JsonObject;
  value: Json;
  onChange: (value: Json) => void;
  errors?: Record<string, string>;
}) {
  const id = useId();
  function control(
    node: JsonObject,
    current: Json | undefined,
    update: (value: Json | undefined) => void,
    key: string,
    path: string,
  ) {
    const label = taskFieldLabel(key);
    const inputId = `${id}-${path}`;
    if (node.type === "object" && isJsonObject(node.properties ?? null)) {
      const object = isJsonObject(current ?? null)
        ? (current as JsonObject)
        : {};
      const required = Array.isArray(node.required) ? node.required : [];
      return (
        <div className="flex flex-col gap-4">
          {Object.entries(node.properties as JsonObject).map(
            ([field, spec]) =>
              isJsonObject(spec) && (
                <div key={field} className="flex flex-col gap-2">
                  {!required.includes(field) && (
                    <label className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={Object.hasOwn(object, field)}
                        onChange={(e) => {
                          const next = { ...object };
                          if (e.target.checked)
                            next[field] =
                              spec.default ??
                              (spec.type === "boolean"
                                ? false
                                : spec.type === "array"
                                  ? []
                                  : "");
                          else delete next[field];
                          update(next);
                        }}
                      />
                      填写{taskFieldLabel(field)}（可选）
                    </label>
                  )}
                  {(required.includes(field) || Object.hasOwn(object, field)) &&
                    control(
                      spec,
                      object[field],
                      (next) => {
                        const copy = { ...object };
                        if (next === undefined) delete copy[field];
                        else copy[field] = next;
                        update(copy);
                      },
                      field,
                      `${path}.${field}`,
                    )}
                </div>
              ),
          )}
        </div>
      );
    }
    const type = Array.isArray(node.type)
      ? node.type.find((t) => t !== "null")
      : node.type;
    const nullable = Array.isArray(node.type) && node.type.includes("null");
    return (
      <div className="flex flex-col gap-2">
        <Label htmlFor={inputId}>{label}</Label>
        {nullable && (
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={current === null}
              onChange={(e) =>
                update(
                  e.target.checked
                    ? null
                    : type === "array"
                      ? []
                      : type === "boolean"
                        ? false
                        : "",
                )
              }
            />
            使用空值
          </label>
        )}
        {current !== null &&
          (type === "boolean" ? (
            <label className="flex items-center gap-2 text-sm">
              <input
                id={inputId}
                type="checkbox"
                checked={current === true}
                onChange={(e) => update(e.target.checked)}
              />
              开启
            </label>
          ) : type === "array" && isJsonObject(node.items ?? null) ? (
            <div className="flex flex-col gap-2">
              {(Array.isArray(current) ? current : []).map((item, index) => (
                <div className="flex items-start gap-2" key={index}>
                  <div className="min-w-0 flex-1">
                    {control(
                      node.items as JsonObject,
                      item,
                      (next) =>
                        update(
                          (current as Json[]).map((v, i) =>
                            i === index ? (next ?? null) : v,
                          ),
                        ),
                      `${label} ${index + 1}`,
                      `${path}.${index}`,
                    )}
                  </div>
                  <Button
                    variant="ghost"
                    aria-label={`删除${label} ${index + 1}`}
                    onClick={() =>
                      update((current as Json[]).filter((_, i) => i !== index))
                    }
                  >
                    删除
                  </Button>
                </div>
              ))}
              <Button
                variant="outline"
                onClick={() =>
                  update([...(Array.isArray(current) ? current : []), ""])
                }
              >
                添加{label}
              </Button>
            </div>
          ) : Array.isArray(node.enum) ? (
            <select
              id={inputId}
              className="h-9 rounded-md border border-input bg-background px-3"
              value={JSON.stringify(current)}
              onChange={(e) => update(JSON.parse(e.target.value) as Json)}
            >
              {node.enum.map((option, i) => (
                <option key={i} value={JSON.stringify(option)}>
                  {String(option)}
                </option>
              ))}
            </select>
          ) : type === "null" ? (
            <p>空值</p>
          ) : ["text", "question"].includes(key) ? (
            <Textarea
              id={inputId}
              value={typeof current === "string" ? current : ""}
              placeholder={examples[key]}
              onChange={(e) => update(e.target.value)}
              maxLength={
                typeof node.maxLength === "number" ? node.maxLength : undefined
              }
              rows={key === "text" ? 8 : 4}
              aria-invalid={Boolean(errors[path])}
            />
          ) : (
            <Input
              id={inputId}
              type={type === "integer" || type === "number" ? "number" : "text"}
              value={
                typeof current === "string" || typeof current === "number"
                  ? current
                  : ""
              }
              placeholder={examples[key]}
              onChange={(e) =>
                update(
                  type === "integer" || type === "number"
                    ? e.target.value === ""
                      ? undefined
                      : Number(e.target.value)
                    : e.target.value,
                )
              }
              aria-invalid={Boolean(errors[path])}
            />
          ))}
        {errors[path] && (
          <p role="alert" className="text-sm text-destructive">
            {errors[path]}
          </p>
        )}
      </div>
    );
  }
  return control(
    schema,
    value,
    (next) => onChange(next ?? null),
    "业务信息",
    "parameters",
  );
}
