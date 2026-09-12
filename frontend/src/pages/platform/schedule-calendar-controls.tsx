import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Checkbox } from "@/components/ui/checkbox";
import { ChoiceField, Field, TextField } from "@/components/shared/form-field";
import {
  calendarFields, weekdays, encodeCalendar, encodeInterval,
  type CalendarField, type CalendarTiming, type IntervalTiming,
} from "@/lib/schedule-calendar";

function CalendarSelection({ field, values, onChange }: {
  field: CalendarField; values: number[] | null; onChange: (values: number[] | null) => void;
}) {
  const { label, min, max, unit } = calendarFields[field];
  const [range, setRange] = useState<{ start: number; end: number; step: number }>({ start: min, end: max, step: 1 });
  const [multiple, setMultiple] = useState(false);
  const valueLabel = (value: number) => field === "weekday" ? weekdays[value] : `${value}${unit}`;
  const allValues = Array.from({ length: max - min + 1 }, (_, index) => index + min);
  const allLabel = { month: "每个月", day: "每天", weekday: "每天", hour: "每小时", minute: "每分钟", second: "每秒", year: "每年" }[field];
  return <Field label={label}>
    <ChoiceField label={`${label}范围`} value={values === null ? "all" : multiple || values.length > 1 ? "selected" : "single"}
      options={[{ value: "all", label: allLabel }, { value: "single", label: "选择一个" }, { value: "selected", label: "选择多个或按间隔" }]}
      onChange={value => { setMultiple(value === "selected"); onChange(value === "all" ? null : [values?.[0] ?? min]); }} />
    {values !== null && !multiple && values.length === 1 && <ChoiceField label={`${label}选择`} value={String(values[0])} options={allValues.map(value => ({ value: String(value), label: valueLabel(value) }))} onChange={value => onChange([Number(value)])} />}
    {values !== null && (multiple || values.length > 1) && <>
      <div className="flex flex-wrap gap-2" role="group" aria-label={`${label}选择`}>
        {allValues.map(value => <label key={value} className="flex items-center gap-2 rounded bg-ui-surface-grouped px-2 py-1 text-sm">
          <Checkbox aria-label={`${label} ${valueLabel(value)}`} checked={values.includes(value)}
            onCheckedChange={checked => {
              const next = checked ? [...values, value].sort((a, b) => a - b) : values.filter(item => item !== value);
              if (next.length) onChange(next);
            }} />
          {valueLabel(value)}
        </label>)}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        {field === "weekday" ? <>
          <ChoiceField label="执行星期起点" value={String(range.start)} options={allValues.map(value => ({ value: String(value), label: valueLabel(value) }))} onChange={value => setRange(current => ({ ...current, start: Number(value) }))} />
          <ChoiceField label="执行星期终点" value={String(range.end)} options={allValues.map(value => ({ value: String(value), label: valueLabel(value) }))} onChange={value => setRange(current => ({ ...current, end: Number(value) }))} />
        </> : <>
        <label className="flex flex-col gap-1 text-sm">从
          <Input className="w-24" aria-label={`${label}起点`} type="number" min={min} max={max} value={range.start}
            onChange={event => setRange(current => ({ ...current, start: Number(event.target.value) }))} />
        </label>
        <label className="flex flex-col gap-1 text-sm">到
          <Input className="w-24" aria-label={`${label}终点`} type="number" min={min} max={max} value={range.end}
            onChange={event => setRange(current => ({ ...current, end: Number(event.target.value) }))} />
        </label>
        </>}
        <label className="flex flex-col gap-1 text-sm">每隔
          <Input className="w-24" aria-label={`${label}间隔`} type="number" min={1} max={max - min + 1} value={range.step}
            onChange={event => setRange(current => ({ ...current, step: Number(event.target.value) }))} />
        </label>
        <Button variant="outline" disabled={![range.start, range.end, range.step].every(Number.isInteger) || range.start < min || range.end > max || range.start > range.end || range.step < 1}
          onClick={() => onChange(allValues.filter(value => value >= range.start && value <= range.end && (value - range.start) % range.step === 0))}>
          应用{label}区间
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">至少保留一项。区间选择会替换此处已选内容。</p>
    </>}
  </Field>;
}
export function ScheduleCalendarControls({ calendar, onChange }: { calendar: CalendarTiming; onChange: (source: string) => void }) {
  return <div className="flex flex-col gap-4">
    <p className="text-sm text-muted-foreground">在所选日期、星期和时刻同时满足时执行。不存在的日期会跳过。</p>
    {(Object.keys(calendarFields) as CalendarField[]).map(field =>
      <CalendarSelection key={field} field={field} values={calendar.values[field]}
        onChange={values => onChange(encodeCalendar({ ...calendar, values: { ...calendar.values, [field]: values } }))} />)}
  </div>;
}
export function ScheduleIntervalControls({ interval, onChange }: { interval: IntervalTiming; onChange: (source: string) => void }) {
  const [unit, setUnit] = useState(() => [86400, 3600, 60, 1].find(size => interval.seconds % size === 0)!);
  const [anchor, setAnchor] = useState(() => {
    const now = Date.now();
    const base = Math.floor(now / (interval.seconds * 1000)) * interval.seconds * 1000;
    return new Date(base + (interval.phase % interval.seconds) * 1000).toISOString().slice(0, 19);
  });
  return <div className="flex flex-col gap-4">
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <TextField label="每隔" type="number" value={String(interval.seconds / unit)} onChange={value => {
        const seconds = Number(value) * unit;
        if (Number.isInteger(seconds) && seconds >= 1) {
          const reference = Date.parse(`${anchor}Z`) / 1000;
          onChange(encodeInterval({ ...interval, seconds, phase: ((reference % seconds) + seconds) % seconds }));
        }
      }} />
      <ChoiceField label="间隔单位" value={String(unit)} options={[
        { value: "86400", label: "天" }, { value: "3600", label: "小时" }, { value: "60", label: "分钟" }, { value: "1", label: "秒" },
      ]} onChange={value => setUnit(Number(value))} />
    </div>
    <Field label="参考起点（协调世界时）"><Input aria-label="参考起点（协调世界时）" type="datetime-local" step={1} value={anchor} onChange={event => {
      const value = event.target.value;
      const seconds = Date.parse(`${value}Z`) / 1000;
      if (Number.isFinite(seconds)) {
        setAnchor(value);
        onChange(encodeInterval({ ...interval, phase: ((seconds % interval.seconds) + interval.seconds) % interval.seconds }));
      }
    }} /></Field>
    <p className="text-sm text-muted-foreground">从参考起点按固定时长重复，过去的时间不会重新执行。固定间隔不随夏令时改变；具体下次时间请查看预览。</p>
  </div>;
}
