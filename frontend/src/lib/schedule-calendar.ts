/** UI value codec for the installed calendar contract; firing dates come from the server. */
export const calendarFields = {
  month: { label: "执行月份", min: 1, max: 12, unit: "月" },
  day: { label: "每月日期", min: 1, max: 31, unit: "日" },
  weekday: { label: "执行星期", min: 0, max: 6, unit: "" },
  hour: { label: "执行小时", min: 0, max: 23, unit: "时" },
  minute: { label: "每小时的分钟", min: 0, max: 59, unit: "分" },
  second: { label: "每分钟的秒数", min: 0, max: 59, unit: "秒" },
  year: { label: "执行年份", min: 2000, max: 2100, unit: "年" },
} as const;
export type CalendarField = keyof typeof calendarFields;
export type CalendarValues = Record<CalendarField, number[] | null>;
export type CalendarTiming = { source: string; values: CalendarValues };
export type IntervalTiming = { source: string; seconds: number; phase: number };
export const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
const monthNames = "january february march april may june july august september october november december".split(" ");
const dayNames = "sunday monday tuesday wednesday thursday friday saturday".split(" ");
const aliases: Record<string, string> = {
  "@yearly": "0 0 1 1 *", "@annually": "0 0 1 1 *", "@monthly": "0 0 1 * *",
  "@weekly": "0 0 * * 0", "@daily": "0 0 * * *", "@midnight": "0 0 * * *", "@hourly": "0 * * * *",
};
function parts(source: string) {
  const value = source.split("#", 1)[0].trim();
  return (aliases[value] ?? value).split(/\s+/);
}
function parseField(text: string, field: CalendarField): number[] | null | undefined {
  const { min, max } = calendarFields[field];
  if (text === "*") return null;
  const upper = field === "weekday" ? 7 : max;
  const parse = (token: string) => {
    if (/^\+?\d+$/.test(token)) return Number(token);
    const names = field === "month" ? monthNames : field === "weekday" ? dayNames : [];
    if (token.length < (field === "month" ? 3 : 2)) return NaN;
    const index = names.findIndex(name => name.startsWith(token.toLowerCase()));
    return index < 0 ? NaN : index + (field === "month" ? 1 : 0);
  };
  const values = new Set<number>();
  for (const part of text.split(",")) {
    const [range, stride, extra] = part.split("/");
    const step = stride === undefined ? 1 : Number(stride);
    if (extra !== undefined || !/^\+?\d+$/.test(stride ?? "1") || step < 1) return undefined;
    const endpoints = range.split("-");
    if (endpoints.length > 2) return undefined;
    const start = range === "*" ? min : parse(endpoints[0]);
    const end = range === "*" ? upper : endpoints.length === 2 ? parse(endpoints[1]) : stride ? upper : start;
    if (!Number.isFinite(start) || !Number.isFinite(end) || start < min || end > upper || start > end) return undefined;
    for (let value = start; value <= end; value += step) values.add(field === "weekday" && value === 7 ? 0 : value);
  }
  return values.size === max - min + 1 ? null : [...values].sort((a, b) => a - b);
}
export function decodeCalendar(source: string): CalendarTiming | null {
  const tokens = parts(source);
  if (tokens.length < 5 || tokens.length > 7) return null;
  const [second, minute, hour, day, month, weekday, year] = tokens.length === 7 ? tokens : ["0", ...tokens, ...(tokens.length === 5 ? ["*"] : [])];
  const raw = { second, minute, hour, day, month, weekday, year };
  const values = {} as CalendarValues;
  for (const key of Object.keys(calendarFields) as CalendarField[]) {
    const value = parseField(raw[key], key);
    if (value === undefined) return null;
    values[key] = value;
  }
  return { source, values };
}
function compact(values: number[] | null, field: CalendarField) {
  if (values === null) return "*";
  const sorted = [...new Set(values)].sort((a, b) => a - b);
  const { min, max } = calendarFields[field];
  if (sorted.length === max - min + 1) return "*";
  const output: string[] = [];
  for (let index = 0; index < sorted.length;) {
    const start = sorted[index];
    const step = sorted[index + 1] - start;
    let end = index + 1;
    while (end + 1 < sorted.length && sorted[end + 1] - sorted[end] === step) end++;
    if (end < sorted.length && (end - index >= 2 || (step === 1 && end > index))) {
      output.push(`${start}-${sorted[end]}${step === 1 ? "" : `/${step}`}`);
      index = end + 1;
    } else { output.push(String(start)); index++; }
  }
  return output.join(",");
}
export function encodeCalendar(timing: CalendarTiming): string {
  const original = decodeCalendar(timing.source);
  const tokens = parts(timing.source);
  const fieldOrder: CalendarField[] = ["second", "minute", "hour", "day", "month", "weekday", "year"];
  const raw = tokens.length === 7 ? tokens : ["0", ...tokens, ...(tokens.length === 5 ? ["*"] : [])];
  let changed = false;
  const fields = fieldOrder.map((field, index) => {
    if (original && JSON.stringify(original.values[field]) === JSON.stringify(timing.values[field])) return raw[index];
    changed = true;
    return compact(timing.values[field], field);
  });
  if (!changed) return timing.source;
  const length = tokens.length === 7 || fields[0] !== "0" ? 7 : tokens.length === 6 || fields[6] !== "*" ? 6 : 5;
  const commentAt = timing.source.indexOf("#");
  const comment = commentAt < 0 ? "" : ` ${timing.source.slice(commentAt)}`;
  return (length === 7 ? fields : fields.slice(1, length + 1)).join(" ") + comment;
}
function duration(text: string): number | null {
  if (/^\+?0$/.test(text)) return 0;
  const units: Record<string, number> = { ns: 1e-9, us: 1e-6, "µs": 1e-6, "μs": 1e-6, ms: .001, s: 1, m: 60, h: 3600, d: 86400 };
  const matches = [...text.matchAll(/(\d+(?:\.\d*)?|\.\d+)(ns|us|µs|μs|ms|s|m|h|d)/g)];
  if (!matches.length || matches.map(match => match[0]).join("") !== text.replace(/^\+/, "")) return null;
  return Math.floor(matches.reduce((sum, match) => sum + Number(match[1]) * units[match[2]], 0));
}
export function decodeInterval(source: string): IntervalTiming | null {
  const match = /^@every\s+([^/\s]+)(?:\/([^/\s]+))?$/.exec(source.split("#", 1)[0].trim());
  if (!match) return null;
  const seconds = duration(match[1]), phase = duration(match[2] ?? "0");
  return seconds && phase !== null ? { source, seconds, phase } : null;
}
export function encodeInterval(timing: IntervalTiming) {
  const original = decodeInterval(timing.source);
  if (original?.seconds === timing.seconds && original.phase === timing.phase) return timing.source;
  const commentAt = timing.source.indexOf("#");
  return `@every ${timing.seconds}s${timing.phase ? `/${timing.phase}s` : ""}${commentAt < 0 ? "" : ` ${timing.source.slice(commentAt)}`}`;
}
export function durationLabel(seconds: number) {
  for (const [size, label] of [[86400, "天"], [3600, "小时"], [60, "分钟"], [1, "秒"]] as const)
    if (seconds % size === 0) return `${seconds / size} ${label}`;
  return `${seconds} 秒`;
}
