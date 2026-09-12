import { useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
import {
  asInputSchema,
  inputLabel,
  newInputValue,
  valueTypeLabels,
} from "@/lib/platform-authoring/schema/input-values";
import { TYPED_CONSTRAINTS } from "@/lib/platform-authoring/schema/constraints";
import { ValueEditor } from "../generated-form/value-editor";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

export type JsonSchemaEditorProps = {
  label: string;
  schema: JsonObject;
  onChange: (schema: JsonObject) => void;
  disabled?: boolean;
};

const limits: Record<string, string> = {
  minLength: "最少字符数",
  maxLength: "最多字符数",
  minimum: "最小值（包含）",
  maximum: "最大值（包含）",
  exclusiveMinimum: "必须大于",
  exclusiveMaximum: "必须小于",
  multipleOf: "数值间隔",
  minItems: "最少项目数",
  maxItems: "最多项目数",
  minProperties: "最少填写字段数",
  maxProperties: "最多填写字段数",
};

function without(schema: JsonObject, ...keys: string[]) {
  const next = { ...schema };
  keys.forEach((key) => delete next[key]);
  return next;
}

function valueRules(schema: JsonObject) {
  return without(
    schema,
    "title",
    "description",
    "default",
    "examples",
    "enum",
    "const",
  );
}

function RuleToggle({
  label,
  checked,
  disabled,
  onChange,
  description,
}: {
  label: string;
  checked: boolean;
  disabled: boolean;
  onChange: (checked: boolean) => void;
  description?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <div>
        <p className="text-sm font-medium">{label}</p>
        {description && (
          <p className="text-sm text-muted-foreground">{description}</p>
        )}
      </div>
      <Switch
        aria-label={label}
        checked={checked}
        disabled={disabled}
        onCheckedChange={onChange}
      />
    </div>
  );
}

function ValueRulesEditor({
  label,
  schema,
  onChange,
  disabled = false,
}: JsonSchemaEditorProps) {
  const rules = valueRules(schema);
  const hasDefault = Object.hasOwn(schema, "default");
  const hasConstant = Object.hasOwn(schema, "const");
  const choices = Array.isArray(schema.enum) ? schema.enum : null;
  const examples = Array.isArray(schema.examples) ? schema.examples : null;
  const annotate = (key: string, value: Json) =>
    onChange({
      ...schema,
      [key]: value,
      "x-signaldeck-schema": "signaldeck.schema/2",
    });
  return (
    <div className="flex flex-col gap-4">
      <RuleToggle
        label={`${label}使用固定内容`}
        checked={hasConstant}
        disabled={disabled}
        onChange={(checked) =>
          onChange(
            checked
              ? { ...schema, const: newInputValue(rules, false) }
              : without(schema, "const"),
          )
        }
      />
      {hasConstant && (
        <ValueEditor
          label="固定内容"
          schema={rules}
          value={schema.const}
          disabled={disabled}
          onChange={(value) => onChange({ ...schema, const: value })}
        />
      )}
      <RuleToggle
        label={`${label}限制为指定选项`}
        checked={choices !== null}
        disabled={disabled}
        onChange={(checked) =>
          onChange(
            checked
              ? { ...schema, enum: [newInputValue(rules, false)] }
              : without(schema, "enum"),
          )
        }
      />
      {choices && (
        <div className="flex flex-col gap-3">
          {choices.map((value, index) => (
            <div key={index} className="flex flex-col gap-2">
              <ValueEditor
                label={`选项 ${index + 1}`}
                schema={rules}
                value={value}
                disabled={disabled}
                onChange={(next) =>
                  onChange({
                    ...schema,
                    enum: choices.map((current, at) =>
                      at === index ? next : current,
                    ),
                  })
                }
              />
              <Button
                className="self-end"
                type="button"
                variant="ghost"
                disabled={disabled || choices.length === 1}
                onClick={() =>
                  onChange({
                    ...schema,
                    enum: choices.filter((_, at) => at !== index),
                  })
                }
              >
                删除选项 {index + 1}
              </Button>
            </div>
          ))}
          <Button
            className="self-start"
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={() =>
              onChange({
                ...schema,
                enum: [...choices, newInputValue(rules, false)],
              })
            }
          >
            添加选项
          </Button>
        </div>
      )}
      <RuleToggle
        label={`${label}预填内容`}
        checked={hasDefault}
        disabled={disabled}
        description="仅用于新建任务。已经填写或保存的内容会保留。"
        onChange={(checked) =>
          checked
            ? annotate(
                "default",
                newInputValue(without(schema, "default"), false),
              )
            : onChange(without(schema, "default"))
        }
      />
      {hasDefault && (
        <ValueEditor
          label="新任务预填内容"
          schema={without(
            schema,
            "title",
            "description",
            "default",
            "examples",
          )}
          value={schema.default}
          disabled={disabled}
          onChange={(value) => annotate("default", value)}
        />
      )}
      <RuleToggle
        label={`${label}填写示例`}
        checked={examples !== null}
        disabled={disabled}
        onChange={(checked) =>
          checked
            ? annotate("examples", [])
            : onChange(without(schema, "examples"))
        }
      />
      {examples && (
        <div className="flex flex-col gap-3">
          {examples.map((value, index) => (
            <div key={index} className="flex flex-col gap-2">
              <ValueEditor
                label={`示例 ${index + 1}`}
                schema={without(
                  schema,
                  "title",
                  "description",
                  "default",
                  "examples",
                )}
                value={value}
                disabled={disabled}
                onChange={(next) =>
                  annotate(
                    "examples",
                    examples.map((current, at) =>
                      at === index ? next : current,
                    ),
                  )
                }
              />
              <Button
                className="self-end"
                type="button"
                variant="ghost"
                disabled={disabled}
                onClick={() =>
                  annotate(
                    "examples",
                    examples.filter((_, at) => at !== index),
                  )
                }
              >
                删除示例 {index + 1}
              </Button>
            </div>
          ))}
          <Button
            className="self-start"
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={() =>
              annotate("examples", [
                ...examples,
                newInputValue(without(schema, "default"), false),
              ])
            }
          >
            添加示例
          </Button>
        </div>
      )}
    </div>
  );
}

/** Edits the saved closed contract directly so annotations and compound values stay exact. */
export function JsonSchemaEditor({
  label,
  schema,
  onChange,
  disabled = false,
}: JsonSchemaEditorProps) {
  const [typeDrafts, setTypeDrafts] = useState<Record<string, JsonObject>>({});
  const kind = typeof schema.type === "string" ? schema.type : "";
  const fields = asInputSchema(schema.properties);
  const required = Array.isArray(schema.required) ? schema.required : [];
  const title = inputLabel(schema, label);

  function changeType(nextKind: string) {
    setTypeDrafts((current) => ({ ...current, [kind]: schema }));
    const common = without(
      schema,
      ...(TYPED_CONSTRAINTS[kind] ?? []),
      "properties",
      "required",
      "items",
    );
    onChange(
      typeDrafts[nextKind] ?? {
        ...common,
        type: nextKind,
        ...(nextKind === "object" ? { properties: {}, required: [] } : {}),
        ...(nextKind === "array" ? { items: { type: "string" } } : {}),
      },
    );
  }

  function updateField(key: string, field: JsonObject) {
    onChange({ ...schema, properties: { ...fields, [key]: field } });
  }

  function addField() {
    let index = Object.keys(fields).length + 1;
    while (Object.hasOwn(fields, `field_${index}`)) index += 1;
    const key = `field_${index}`;
    onChange({
      ...schema,
      properties: {
        ...fields,
        [key]: { type: "string", title: `字段 ${index}` },
      },
      required: [...required, key],
    });
  }

  return (
    <section className="flex flex-col gap-4 rounded-md border border-border/70 bg-card p-4">
      <h3 className="text-sm font-semibold">{label}</h3>
      <div className="grid gap-3 sm:grid-cols-2">
        <div className="flex flex-col gap-2">
          <Label>名称</Label>
          <Input
            aria-label={`${label}名称`}
            disabled={disabled}
            placeholder={label}
            value={typeof schema.title === "string" ? schema.title : ""}
            onChange={(event) =>
              onChange(
                event.target.value
                  ? { ...schema, title: event.target.value }
                  : without(schema, "title"),
              )
            }
          />
        </div>
        <div className="flex flex-col gap-2">
          <Label>填写方式</Label>
          <Select value={kind} disabled={disabled} onValueChange={changeType}>
            <SelectTrigger aria-label={`${label}填写方式`}>
              <SelectValue placeholder="选择填写方式" />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(valueTypeLabels).map(([value, text]) => (
                <SelectItem key={value} value={value}>
                  {text}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>
      <div className="flex flex-col gap-2">
        <Label>填写提示</Label>
        <Textarea
          aria-label={`${label}填写提示`}
          disabled={disabled}
          rows={2}
          value={
            typeof schema.description === "string" ? schema.description : ""
          }
          onChange={(event) =>
            onChange(
              event.target.value
                ? { ...schema, description: event.target.value }
                : without(schema, "description"),
            )
          }
        />
      </div>
      {kind === "object" && (
        <div className="flex flex-col gap-3">
          {Object.keys(fields).length === 0 && (
            <p className="text-sm text-muted-foreground">
              尚未添加字段。任务可以不收集输入。
            </p>
          )}
          {Object.entries(fields).map(([key, field], index) => (
            <div key={key} className="flex flex-col gap-3">
              <JsonSchemaEditor
                label={`字段 ${index + 1}`}
                schema={asInputSchema(field)}
                disabled={disabled}
                onChange={(next) => updateField(key, next)}
              />
              <div className="flex flex-wrap items-center justify-between gap-3">
                <RuleToggle
                  label={`${inputLabel(asInputSchema(field), `字段 ${index + 1}`)}必填`}
                  checked={required.includes(key)}
                  disabled={disabled}
                  onChange={(checked) =>
                    onChange({
                      ...schema,
                      required: checked
                        ? [...required.filter((item) => item !== key), key]
                        : required.filter((item) => item !== key),
                    })
                  }
                />
                <Button
                  type="button"
                  variant="ghost"
                  disabled={disabled}
                  onClick={() =>
                    onChange({
                      ...schema,
                      properties: without(fields, key),
                      required: required.filter((item) => item !== key),
                    })
                  }
                >
                  <Trash2 data-icon="inline-start" />
                  删除字段 {index + 1}
                </Button>
              </div>
            </div>
          ))}
          <Button
            className="self-start"
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={addField}
          >
            <Plus data-icon="inline-start" />
            添加字段
          </Button>
        </div>
      )}
      {kind === "array" && (
        <JsonSchemaEditor
          label="每项内容"
          schema={asInputSchema(schema.items)}
          disabled={disabled}
          onChange={(items) => onChange({ ...schema, items })}
        />
      )}
      <div className="grid gap-3 sm:grid-cols-2">
        {(TYPED_CONSTRAINTS[kind] ?? [])
          .filter((key) => key in limits)
          .map((key) => (
            <div key={key} className="flex flex-col gap-2">
              <Label>{limits[key]}</Label>
              <Input
                type="number"
                aria-label={`${label}${limits[key]}`}
                disabled={disabled}
                value={typeof schema[key] === "number" ? schema[key] : ""}
                onChange={(event) =>
                  onChange(
                    event.target.value === ""
                      ? without(schema, key)
                      : { ...schema, [key]: Number(event.target.value) },
                  )
                }
              />
            </div>
          ))}
      </div>
      {kind === "array" && (
        <RuleToggle
          label={`${title}项目不能重复`}
          checked={schema.uniqueItems === true}
          disabled={disabled}
          onChange={(checked) => onChange({ ...schema, uniqueItems: checked })}
        />
      )}
      <ValueRulesEditor
        label={title}
        schema={schema}
        disabled={disabled}
        onChange={onChange}
      />
    </section>
  );
}
