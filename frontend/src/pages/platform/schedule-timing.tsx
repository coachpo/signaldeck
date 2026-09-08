import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, TextField, ChoiceField } from "@/components/shared/form-field";
import {
  decodeFrequency,
  encodeFrequency,
  scheduleSummary,
  weekdays,
  type Frequency,
} from "@/lib/schedule-frequency";
import {
  useSchedulePreview,
  useAppliedSchedulePreview,
  type SchedulePreview,
} from "@/hooks/use-schedule-preview";
import type { ScheduleConfig } from "@/lib/types/workflow-platform";

function PreviewTimes({ preview }: { preview: SchedulePreview }) {
  return (
    <div className="flex flex-col gap-1 text-sm">
      <p>
        {preview.scope === "draft"
          ? "时间预览，不会启用自动执行"
          : preview.paused
            ? "已暂停，以下仅供核对时间，不会自动执行"
            : "接下来计划执行的时间"}
      </p>
      {preview.scope === "applied" &&
        preview.desiredRevision !== preview.syncedRevision && (
          <p role="status">
            修改尚未完成同步。以下时间属于调度服务当前生效的安排，不代表新配置已确认生效。
          </p>
        )}
      {preview.times.length ? (
        <ul>
          {preview.times.map((time) => (
            <li key={time}>
              <time dateTime={time}>
                {new Intl.DateTimeFormat(undefined, {
                  dateStyle: "medium",
                  timeStyle: "short",
                  timeZone: preview.timeZone,
                }).format(new Date(time))}
              </time>{" "}
              · {preview.timeZone}
            </li>
          ))}
        </ul>
      ) : (
        <p>未查到后续执行时间。</p>
      )}
      {preview.scope === "applied" && (
        <p>
          已生效：{preview.appliedNote || "未知版本"}；待应用版本：
          {preview.desiredRevision}。
        </p>
      )}
      <p className="text-muted-foreground">
        查询时间：{new Date(preview.observedAt).toLocaleString()}
        。夏令时切换时，以调度服务返回的实际时间为准。
      </p>
    </div>
  );
}
export function AppliedSchedulePreview({
  id,
  revision,
}: {
  id: string;
  revision: number;
}) {
  const query = useAppliedSchedulePreview(id, revision);
  return (
    <div className="text-sm">
      {query.data ? (
        <PreviewTimes preview={query.data} />
      ) : (
        <p>
          {query.isPending
            ? "正在核对下次时间…"
            : "暂时无法查询下次时间，已保存的安排与历史仍可查看。"}
        </p>
      )}
    </div>
  );
}
export function ScheduleTiming({
  draft,
  onChange,
}: {
  draft: ScheduleConfig;
  onChange: (value: ScheduleConfig) => void;
}) {
  const frequency = decodeFrequency(draft.cron);
  const [advanced, setAdvanced] = useState(false);
  const preview = useSchedulePreview();
  const [previewKey, setPreviewKey] = useState("");
  const key = JSON.stringify([draft.cron, draft.timeZone]);
  const change = (partial: Partial<Frequency>) =>
    onChange({
      ...draft,
      cron: encodeFrequency({ ...frequency!, ...partial }),
    });
  return (
    <div className="flex flex-col gap-4">
      <ChoiceField
        label="重复频率"
        value={frequency?.kind ?? "custom"}
        options={[
          { value: "daily", label: "每天" },
          { value: "weekly", label: "每周" },
          { value: "monthly", label: "每月" },
          { value: "custom", label: "自定义安排" },
        ]}
        onChange={(value) => {
          if (value === "custom") {
            setAdvanced(true);
            return;
          }
          onChange({
            ...draft,
            cron: encodeFrequency({
              ...(frequency ?? { hour: 9, minute: 0, day: 1 }),
              kind: value as Frequency["kind"],
              day: frequency?.kind === value ? frequency.day : 1,
            }),
          });
        }}
      />
      {frequency && (
        <>
          {frequency.kind === "weekly" && (
            <ChoiceField
              label="星期"
              value={String(frequency.day)}
              options={weekdays.map((label, value) => ({
                label,
                value: String(value),
              }))}
              onChange={(day) => change({ day: Number(day) })}
            />
          )}
          {frequency.kind === "monthly" && (
            <ChoiceField
              label="每月日期"
              value={String(frequency.day)}
              options={Array.from({ length: 31 }, (_, i) => ({
                value: String(i + 1),
                label: String(i + 1),
              }))}
              onChange={(day) => change({ day: Number(day) })}
            />
          )}
          <TextField
            label="当地时间"
            type="time"
            value={`${String(frequency.hour).padStart(2, "0")}:${String(frequency.minute).padStart(2, "0")}`}
            onChange={(time) => {
              if (time) {
                const [hour, minute] = time.split(":").map(Number);
                change({ hour, minute });
              }
            }}
          />
        </>
      )}
      {!frequency && (
        <p className="text-sm">
          已保留自定义安排。修改名称或业务信息不会覆盖此时间规则。
        </p>
      )}
      <Field
        label="时区"
        description="保存后时区保持固定，不随旅行地点改变。可搜索或填写城市时区。"
      >
        <Input
          aria-label="时区"
          list="schedule-time-zones"
          value={draft.timeZone}
          onChange={(event) =>
            onChange({ ...draft, timeZone: event.target.value })
          }
        />
        <datalist id="schedule-time-zones">
          {["UTC", ...Intl.supportedValuesOf("timeZone")].map((zone) => (
            <option value={zone} key={zone} />
          ))}
        </datalist>
      </Field>
      <p className="text-sm">
        {scheduleSummary(draft.cron)} · {draft.timeZone}.{" "}
        {frequency?.kind === "monthly" && frequency.day > 28
          ? "没有此日期的月份会跳过。"
          : ""}
      </p>
      <Button variant="outline" onClick={() => setAdvanced((value) => !value)}>
        {advanced ? "收起自定义安排" : "编辑自定义安排"}
      </Button>
      {advanced && (
        <TextField
          label="自定义时间表达式"
          value={draft.cron}
          onChange={(cron) => onChange({ ...draft, cron })}
        />
      )}
      <Button
        variant="outline"
        disabled={preview.isPending}
        onClick={() => {
          setPreviewKey(key);
          preview.mutate({ cron: draft.cron, timeZone: draft.timeZone });
        }}
      >
        预览下次时间
      </Button>
      {previewKey === key && preview.data && (
        <PreviewTimes preview={preview.data} />
      )}
      {previewKey === key && preview.isError && (
        <p role="alert" className="text-sm text-destructive">
          时间预览暂不可用，请检查安排和时区后重试。没有启用自动执行。
        </p>
      )}
    </div>
  );
}
