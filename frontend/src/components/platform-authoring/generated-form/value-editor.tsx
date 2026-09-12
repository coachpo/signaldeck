import { useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import type { Json, JsonObject } from "@/lib/types/workflow-platform";
import {
  asInputSchema,
  inputLabel,
  inputValueIssues,
  inputValuesEqual,
  newInputValue,
  orderedInputKeys,
  valueType,
  valueTypeLabels,
  type InputValueIssue,
} from "@/lib/platform-authoring/schema/input-values";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import type { InputHint } from "./schema-form";

export type ValueEditorProps = {
  label?: string;
  schema?: JsonObject;
  value: Json;
  onChange: (value: Json) => void;
  onValidityChange?: (valid: boolean) => void;
  disabled?: boolean;
  inputHints?: readonly InputHint[];
};

export function ValueSummary({
  value,
  schema = {},
  label,
}: {
  value: Json;
  schema?: JsonObject;
  label?: string;
}) {
  let content;
  if (Array.isArray(value))
    content = value.length ? (
      <ol className="flex list-decimal flex-col gap-2 pl-5">
        {value.map((item, index) => (
          <li key={index}>
            <ValueSummary value={item} schema={asInputSchema(schema.items)} />
          </li>
        ))}
      </ol>
    ) : (
      <span>空列表</span>
    );
  else if (value && typeof value === "object")
    content = Object.keys(value).length ? (
      <dl className="flex flex-col gap-2">
        {Object.entries(value).map(([key, item]) => (
          <div key={key}>
            <dt className="font-medium">
              {inputLabel(
                asInputSchema(asInputSchema(schema.properties)[key]),
                key,
              )}
            </dt>
            <dd className="pl-3">
              <ValueSummary
                value={item}
                schema={asInputSchema(asInputSchema(schema.properties)[key])}
              />
            </dd>
          </div>
        ))}
      </dl>
    ) : (
      <span>未填写字段</span>
    );
  else
    content = (
      <span className="whitespace-pre-wrap break-words">
        {value === null
          ? "空值"
          : value === ""
            ? "空文本"
            : typeof value === "boolean"
              ? value
                ? "是"
                : "否"
              : String(value)}
      </span>
    );
  return (
    <div className="min-w-0 text-sm">
      {label && <p className="mb-1 font-medium">{inputLabel(schema, label)}</p>}
      {content}
    </div>
  );
}

function Choice({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (value: string) => void;
  disabled: boolean;
}) {
  return (
    <Select value={value} onValueChange={onChange} disabled={disabled}>
      <SelectTrigger aria-label={label}>
        <SelectValue placeholder="请选择" />
      </SelectTrigger>
      <SelectContent>
        {options.map((option) => (
          <SelectItem key={option.value} value={option.value}>
            {option.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

type ValueNodeProps = Omit<ValueEditorProps, "value" | "onValidityChange"> & {
  value?: Json;
  path: string[];
  issues: InputValueIssue[];
  required?: boolean;
};

function inputRequirement(schema: JsonObject, required: boolean): string {
  if (!required) return "可选";
  if (inputValueIssues(schema, null).length === 0) return "允许空值";
  if (
    inputValueIssues(schema, "").length === 0 ||
    inputValueIssues(schema, []).length === 0
  ) return "可留空";
  return "必填";
}

function ValueNode({
  label = "输入内容",
  schema = {},
  value,
  onChange,
  disabled = false,
  inputHints = [],
  path,
  issues,
  required,
}: ValueNodeProps) {
  const [newField, setNewField] = useState("");
  const [multiline, setMultiline] = useState(false);
  const [alternatives, setAlternatives] = useState<Record<string, Json>>({});
  const title = inputLabel(schema, label);
  const description =
    typeof schema.description === "string" ? schema.description : undefined;
  const localIssues = issues.filter((issue) =>
    inputValuesEqual(issue.path, path),
  );
  const branches = Array.isArray(schema.anyOf)
    ? schema.anyOf.map(asInputSchema)
    : Array.isArray(schema.type)
      ? schema.type.map((type) => ({ ...schema, type }))
      : [];
  const kind = typeof schema.type === "string" ? schema.type : valueType(value);
  const scalarMismatch =
    value !== undefined &&
    !branches.length &&
    !["object", "array"].includes(kind) &&
    valueType(value) !== (kind === "integer" ? "number" : kind);
  const branchIndex = branches.findIndex(
    (branch) => inputValueIssues(branch, value).length === 0,
  );
  const selectedIndex = branchIndex < 0 ? 0 : branchIndex;
  const child = (
    next: Partial<ValueNodeProps> & {
      label: string;
      onChange: (value: Json) => void;
    },
  ) => (
    <ValueNode
      disabled={disabled}
      inputHints={inputHints}
      issues={issues}
      path={path}
      {...next}
    />
  );
  let control;

  if (branches.length) {
    control = (
      <div className="flex flex-col gap-3">
        <Choice
          label={`${title}填写方式`}
          value={String(selectedIndex)}
          disabled={disabled}
          options={branches.map((branch, index) => ({
            value: String(index),
            label: inputLabel(
              branch,
              valueTypeLabels[String(branch.type)] ?? `选项 ${index + 1}`,
            ),
          }))}
          onChange={(next) => {
            if (value !== undefined)
              setAlternatives((current) => ({
                ...current,
                [selectedIndex]: value,
              }));
            onChange(
              Object.hasOwn(alternatives, next)
                ? alternatives[next]
                : newInputValue(branches[Number(next)]),
            );
          }}
        />
        {child({
          label: title,
          schema: branches[selectedIndex],
          value,
          onChange,
        })}
      </div>
    );
  } else if (Object.hasOwn(schema, "const")) {
    control = (
      <div className="flex flex-col gap-2">
        <ValueSummary value={schema.const} schema={schema} />
        <p className="text-sm text-muted-foreground">此项使用固定内容。</p>
        {!inputValuesEqual(value, schema.const) && (
          <Button
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={() => onChange(structuredClone(schema.const))}
          >
            使用固定内容
          </Button>
        )}
        {value !== undefined && !inputValuesEqual(value, schema.const) && (
          <ValueSummary label="当前填写内容" value={value} schema={schema} />
        )}
      </div>
    );
  } else if (Array.isArray(schema.enum)) {
    const options = schema.enum;
    const selected = options.findIndex((option) =>
      inputValuesEqual(value, option),
    );
    control = (
      <div className="flex flex-col gap-2">
        {options.some(
          (option) => option !== null && typeof option === "object",
        ) ? (
          options.map((option, index) => (
            <div
              key={index}
              className="flex flex-col gap-2 rounded-md border border-border/70 p-3"
            >
              <ValueSummary value={option} schema={schema} />
              <Button
                className="self-start"
                type="button"
                variant={selected === index ? "secondary" : "outline"}
                disabled={disabled}
                onClick={() => onChange(structuredClone(option))}
              >
                {selected === index
                  ? `已选择选项 ${index + 1}`
                  : `选择选项 ${index + 1}`}
              </Button>
            </div>
          ))
        ) : (
          <Choice
            label={title}
            disabled={disabled}
            value={selected < 0 ? "" : String(selected)}
            options={options.map((option, index) => ({
              value: String(index),
              label:
                option === null
                  ? "空值"
                  : typeof option === "boolean"
                    ? option
                      ? "是"
                      : "否"
                    : option === ""
                      ? "空文本"
                      : String(option),
            }))}
            onChange={(next) =>
              onChange(structuredClone(options[Number(next)]))
            }
          />
        )}
        {selected < 0 && value !== undefined && (
          <ValueSummary label="当前填写内容" value={value} />
        )}
      </div>
    );
  } else if (
    (kind === "object" &&
      value !== undefined &&
      (value === null || typeof value !== "object" || Array.isArray(value))) ||
    (kind === "array" && value !== undefined && !Array.isArray(value))
  ) {
    control = (
      <div className="flex flex-col gap-2">
        <ValueSummary label="当前填写内容" value={value!} />
        <p className="text-sm text-muted-foreground">
          原内容仍保留。选择重新填写后，将替换这一项。
        </p>
        <Button
          type="button"
          variant="outline"
          disabled={disabled}
          onClick={() => onChange(newInputValue(schema))}
        >
          重新填写{title}
        </Button>
      </div>
    );
  } else if (kind === "object") {
    const object = asInputSchema(value);
    const fields = asInputSchema(schema.properties);
    const requiredFields = Array.isArray(schema.required)
      ? schema.required
      : [];
    const names = orderedInputKeys(
      [
        ...Object.keys(fields),
        ...Object.keys(object).filter((key) => !Object.hasOwn(fields, key)),
      ],
      path,
      inputHints,
    );
    const generic = schema.type === undefined;
    control = (
      <div className="flex flex-col gap-3">
        {names.length === 0 && (
          <p className="text-sm text-muted-foreground">
            {generic ? "尚未添加字段。" : "此项无需填写字段。"}
          </p>
        )}
        {names.map((key) => {
          const field = asInputSchema(fields[key]);
          const fieldTitle = inputLabel(field, key);
          const present = Object.hasOwn(object, key);
          const needed = requiredFields.includes(key);
          return (
            <div className="flex flex-col gap-2" key={key}>
              {!present && !needed ? (
                <div className="flex items-center justify-between gap-3 rounded-md border border-border/70 p-3">
                  <div>
                    <p className="text-sm font-medium">
                      {fieldTitle}{" "}
                      <span className="font-normal text-muted-foreground">
                        可选
                      </span>
                    </p>
                    {typeof field.description === "string" && (
                      <p className="text-sm text-muted-foreground">
                        {field.description}
                      </p>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={disabled}
                    onClick={() =>
                      onChange({ ...object, [key]: newInputValue(field) })
                    }
                  >
                    添加{fieldTitle}
                  </Button>
                </div>
              ) : (
                <>
                  {child({
                    label: fieldTitle,
                    schema: field,
                    value: object[key],
                    required: needed,
                    path: [...path, key],
                    onChange: (next) => onChange({ ...object, [key]: next }),
                  })}
                  {!needed && (
                    <Button
                      className="self-end"
                      type="button"
                      variant="ghost"
                      size="sm"
                      disabled={disabled}
                      onClick={() => {
                        const next = { ...object };
                        delete next[key];
                        onChange(next);
                      }}
                    >
                      <Trash2 data-icon="inline-start" />
                      移除{fieldTitle}
                    </Button>
                  )}
                </>
              )}
            </div>
          );
        })}
        {generic && (
          <div className="flex flex-wrap items-end gap-2">
            <Input
              aria-label={`${title}新字段名称`}
              placeholder="新字段名称"
              value={newField}
              disabled={disabled}
              onChange={(event) => setNewField(event.target.value)}
            />
            <Button
              type="button"
              variant="outline"
              disabled={
                disabled ||
                !newField.trim() ||
                Object.hasOwn(object, newField.trim())
              }
              onClick={() => {
                onChange({ ...object, [newField.trim()]: "" });
                setNewField("");
              }}
            >
              添加字段
            </Button>
          </div>
        )}
      </div>
    );
  } else if (kind === "array") {
    const items = Array.isArray(value) ? value : [];
    const itemSchema = asInputSchema(schema.items);
    control = (
      <div className="flex flex-col gap-3">
        {items.length === 0 && (
          <p className="text-sm text-muted-foreground">
            暂无项目。可按需添加。
          </p>
        )}
        {items.map((item, index) => (
          <div className="flex flex-col gap-2" key={index}>
            {itemSchema.title && (
              <p className="text-sm font-medium">第 {index + 1} 项</p>
            )}
            {child({
              label: `第 ${index + 1} 项`,
              schema: itemSchema,
              value: item,
              path: [...path, String(index)],
              onChange: (next) =>
                onChange(
                  items.map((current, at) => (at === index ? next : current)),
                ),
            })}
            <Button
              className="self-end"
              type="button"
              variant="ghost"
              size="sm"
              disabled={disabled}
              onClick={() => onChange(items.filter((_, at) => at !== index))}
            >
              <Trash2 data-icon="inline-start" />
              删除第 {index + 1} 项
            </Button>
          </div>
        ))}
        <Button
          className="self-start"
          type="button"
          variant="outline"
          size="sm"
          disabled={disabled}
          onClick={() => onChange([...items, newInputValue(itemSchema)])}
        >
          <Plus data-icon="inline-start" />
          添加项目
        </Button>
      </div>
    );
  } else if (kind === "boolean") {
    control =
      value === undefined ? (
        <Choice
          label={title}
          value=""
          disabled={disabled}
          options={[
            { value: "yes", label: "是" },
            { value: "no", label: "否" },
          ]}
          onChange={(next) => onChange(next === "yes")}
        />
      ) : (
        <div className="flex items-center gap-2">
          <Switch
            aria-label={title}
            checked={value === true}
            disabled={disabled}
            onCheckedChange={onChange}
          />
          <span className="text-sm">{value === true ? "是" : "否"}</span>
        </div>
      );
  } else if (kind === "null") {
    control = (
      <div className="flex flex-col gap-2">
        <p className="text-sm text-muted-foreground">此项为空值，无需填写。</p>
        {value !== null && (
          <Button
            type="button"
            variant="outline"
            disabled={disabled}
            onClick={() => onChange(null)}
          >
            设为空值
          </Button>
        )}
      </div>
    );
  } else if (kind === "integer" || kind === "number") {
    control = (
      <Input
        aria-label={title}
        aria-invalid={localIssues.length > 0}
        type="number"
        inputMode={kind === "integer" ? "numeric" : "decimal"}
        step={kind === "integer" ? 1 : "any"}
        disabled={disabled}
        value={typeof value === "number" ? value : ""}
        onChange={(event) =>
          onChange(
            event.target.value === "" ? null : Number(event.target.value),
          )
        }
      />
    );
  } else {
    const hint = inputHints.find(
      (item) => item.ref === ["workflow", "input", ...path].join("."),
    );
    const props = {
      "aria-label": title,
      "aria-invalid": localIssues.length > 0,
      disabled,
      value: typeof value === "string" ? value : "",
      placeholder: hint?.placeholder,
      onChange: (event: { target: { value: string } }) =>
        onChange(event.target.value),
    };
    control =
      multiline ||
      hint?.control === "textarea" ||
      (typeof value === "string" && /[\r\n]/.test(value)) ? (
        <Textarea {...props} rows={4} />
      ) : (
        <div className="flex flex-col gap-1">
          <Input {...props} />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            className="self-end"
            disabled={disabled}
            aria-label={`${title}多行填写`}
            onClick={() => setMultiline(true)}
          >
            多行填写
          </Button>
        </div>
      );
  }

  return (
    <section className="flex min-w-0 flex-col gap-3 rounded-md border border-border/70 bg-card p-4">
      <div className="flex items-center gap-2">
        <p className="text-sm font-medium">{title}</p>
        {required !== undefined && (
          <span className="text-xs text-muted-foreground">
            {inputRequirement(schema, required)}
          </span>
        )}
      </div>
      {description && (
        <p className="text-sm text-muted-foreground">{description}</p>
      )}
      {scalarMismatch &&
        !Object.hasOwn(schema, "const") &&
        !Array.isArray(schema.enum) && (
          <ValueSummary label="原有内容" value={value!} />
        )}
      {schema.type === undefined &&
        !branches.length &&
        !Object.hasOwn(schema, "const") &&
        !Array.isArray(schema.enum) && (
          <Choice
            label={`${title}内容类型`}
            value={kind}
            disabled={disabled}
            options={Object.entries(valueTypeLabels)
              .filter(([key]) => key !== "integer")
              .map(([key, text]) => ({ value: key, label: text }))}
            onChange={(next) => {
              if (value !== undefined)
                setAlternatives((current) => ({ ...current, [kind]: value }));
              onChange(
                Object.hasOwn(alternatives, next)
                  ? alternatives[next]
                  : newInputValue({ type: next }),
              );
            }}
          />
        )}
      {control}
      {localIssues.map((issue) => (
        <p
          key={issue.message}
          role="alert"
          className="text-sm text-destructive"
        >
          {issue.message}
        </p>
      ))}
    </section>
  );
}

export function ValueEditor({
  label = "输入内容",
  schema = {},
  value,
  onValidityChange,
  ...props
}: ValueEditorProps) {
  const issues = inputValueIssues(schema, value, label);
  const valid = issues.length === 0;
  useEffect(() => {
    onValidityChange?.(valid);
  }, [onValidityChange, valid]);
  return (
    <ValueNode
      {...props}
      label={label}
      schema={schema}
      value={value}
      issues={issues}
      path={[]}
    />
  );
}
