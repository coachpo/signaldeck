import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { modelUsageApi } from "@/lib/api/model-usage";
import { queryKeys } from "@/lib/query-keys";

export function currentUsageDay(
  now = new Date(),
  timezone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
) {
  const parts = new Intl.DateTimeFormat("en", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const value = (type: string) => parts.find((part) => part.type === type)!.value;
  return { date: `${value("year")}-${value("month")}-${value("day")}`, timezone };
}

export function useModelUsage(runId?: string) {
  const [selectedDay, setSelectedDay] = useState(() => currentUsageDay());
  useEffect(() => {
    const timer = setInterval(() => {
      const next = currentUsageDay();
      setSelectedDay((current) =>
        current.date === next.date && current.timezone === next.timezone ? current : next,
      );
    }, 30_000);
    return () => clearInterval(timer);
  }, []);
  const run = useQuery({
    queryKey: queryKeys.platform.modelUsage.run(runId ?? ""),
    queryFn: () => modelUsageApi.run(runId!),
    enabled: !!runId,
    refetchInterval: (query) =>
      ["queued", "running"].includes(query.state.data?.runStatus ?? "") ? 1000 : false,
  });
  const day = useQuery({
    queryKey: queryKeys.platform.modelUsage.day(selectedDay.date, selectedDay.timezone),
    queryFn: () => modelUsageApi.day(selectedDay.date, selectedDay.timezone),
    refetchInterval: 30_000,
  });
  return { run, day, selectedDay };
}
