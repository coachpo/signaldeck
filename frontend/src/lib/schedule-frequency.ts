import { decodeCalendar, decodeInterval, durationLabel, weekdays } from "./schedule-calendar";
/** A lossless UI codec; Temporal alone calculates firing dates. */
export type Frequency = {
  kind: "daily" | "weekly" | "monthly";
  hour: number;
  minute: number;
  day: number;
};
export function decodeFrequency(cron: string): Frequency | null {
  const match = /^(\d{1,2}) (\d{1,2}) (\*|\d{1,2}) \* (\*|[0-6])$/.exec(cron);
  if (!match) return null;
  const [, minuteText, hourText, date, weekday] = match;
  const minute = Number(minuteText),
    hour = Number(hourText);
  if (minute > 59 || hour > 23) return null;
  if (date === "*" && weekday === "*")
    return { kind: "daily", hour, minute, day: 1 };
  if (date === "*")
    return { kind: "weekly", hour, minute, day: Number(weekday) };
  if (weekday === "*" && Number(date) >= 1 && Number(date) <= 31)
    return { kind: "monthly", hour, minute, day: Number(date) };
  return null;
}
export function encodeFrequency(value: Frequency): string {
  return `${value.minute} ${value.hour} ${value.kind === "monthly" ? value.day : "*"} * ${value.kind === "weekly" ? value.day : "*"}`;
}
export function scheduleSummary(cron: string): string {
  const value = decodeFrequency(cron);
  if (!value) {
    const interval = decodeInterval(cron);
    if (interval) return `每隔 ${durationLabel(interval.seconds)}`;
    const calendar = decodeCalendar(cron);
    if (!calendar) return "已保存的重复安排";
    const { month, day, weekday, hour, minute, second, year } = calendar.values;
    const days = [year && `${year.join("、")} 年`, month && `${month.join("、")} 月`, day && `每月 ${day.join("、")} 日`, weekday && weekday.map(d => weekdays[d]).join("、")].filter(Boolean);
    const times = hour && minute && hour.length * minute.length <= 6
      ? hour.flatMap(h => minute.map(m => `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`)).join("、")
      : `${hour ? `${hour.join("、")} 时` : "每小时"} · ${minute ? `第 ${minute.join("、")} 分` : "每分钟"}`;
    return [...(days.length ? days : ["每天"]), times, second === null ? "每秒" : second.some(s => s !== 0) ? `第 ${second.join("、")} 秒` : ""].filter(Boolean).join(" · ");
  }
  const time = `${String(value.hour).padStart(2, "0")}:${String(value.minute).padStart(2, "0")}`;
  return `${value.kind === "daily" ? "每天" : value.kind === "weekly" ? `每${weekdays[value.day]}` : `每月 ${value.day} 日`} ${time}`;
}
export { weekdays };

export function scheduleFireLabel(status: string) {
  return (
    (
      {
        pending: "等待执行",
        launched: "执行中",
        launch_failed: "未能启动",
        succeeded: "已完成",
        failed: "执行失败",
        cancelled: "已取消",
      } as Record<string, string>
    )[status] ?? "状态待确认"
  );
}
