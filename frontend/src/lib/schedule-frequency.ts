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
const weekdays = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"];
export function scheduleSummary(cron: string): string {
  const value = decodeFrequency(cron);
  if (!value) return `自定义安排： ${cron}`;
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
    )[status] ?? status
  );
}
