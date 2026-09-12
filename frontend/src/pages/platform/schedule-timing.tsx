import { useState } from "react";
import { decodeCalendar, decodeInterval } from "@/lib/schedule-calendar";
import { ScheduleCalendarControls, ScheduleIntervalControls } from "./schedule-calendar-controls";
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
            修改尚未生效。以下仍是之前的执行时间，请等待确认后再按新安排操作。
          </p>
        )}
      {preview.times.length ? (
        <ul>
          {preview.times.map((time) => (
            <li key={time}>
              <time dateTime={time}>
                {new Intl.DateTimeFormat(undefined, {
                  dateStyle: "medium",
                  timeStyle: "medium",
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
      <p className="text-muted-foreground">
        查询时间：{new Date(preview.observedAt).toLocaleString()}
        。已按所选时区核对夏令时。
      </p>
    </div>
  );
}
export function AppliedSchedulePreview({
  id,
  revision,
  syncStatus,
}: {
  id: string;
  revision: number;
  syncStatus?: string;
}) {
  const query = useAppliedSchedulePreview(id, revision, syncStatus);
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
      {query.isError && <Button variant="outline" onClick={() => void query.refetch()}>重新核对下次时间</Button>}
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
  const [custom, setCustom] = useState(false);
  const calendar = decodeCalendar(draft.cron);
  const interval = decodeInterval(draft.cron);
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
        value={interval ? "interval" : custom ? "custom" : frequency?.kind ?? "custom"}
        options={[
          { value: "daily", label: "每天" },
          { value: "weekly", label: "每周" },
          { value: "monthly", label: "每月" },
          { value: "custom", label: "组合日期与时刻" },
          { value: "interval", label: "固定间隔" },
        ]}
        onChange={(value) => {
          if (value === "custom") {
            setCustom(true);
            if (!calendar) onChange({ ...draft, cron: "0 9 * * *" });
            return;
          }
          setCustom(false);
          if (value === "interval") {
            onChange({ ...draft, cron: "@every 1h" });
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
      {frequency && !custom && (
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
      {interval && <ScheduleIntervalControls interval={interval} onChange={cron => onChange({ ...draft, cron })} />}
      {calendar && (custom || !frequency) && <ScheduleCalendarControls calendar={calendar} onChange={cron => onChange({ ...draft, cron })} />}
      {!calendar && !interval && <p role="status" className="text-sm">已保留原安排，其他修改不会改变执行时间。选择一种重复频率后可重新安排时间。</p>}
      {(interval && interval.seconds < 60 || calendar && (calendar.values.second === null || calendar.values.second.length > 1)) && <p role="status" className="text-sm">此安排可能在一分钟内执行多次。请确认服务用量，并选择上一次尚未结束时的处理方式。</p>}
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
      <Button
        variant="outline"
        disabled={preview.isPending}
        onClick={() => {
          setPreviewKey(key);
          preview.mutate({ cron: draft.cron, timeZone: draft.timeZone });
        }}
      >
        {preview.isPending ? "正在核对下次时间…" : "预览下次时间"}
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
