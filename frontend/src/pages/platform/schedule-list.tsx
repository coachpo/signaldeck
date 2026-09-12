import { useState } from "react";
import { useUnsavedWork } from "@/hooks/use-unsaved-work";
import { scheduleTriggerDrafts } from "./schedule-drafts";
import { ApiRequestError } from "@/lib/api-client";
import { Link } from "react-router";
import { Button } from "@/components/ui/button";
import { InventoryPageShell } from "@/components/shared/inventory-page-shell";
import { InventoryStatePanel } from "@/components/shared/inventory-state-panel";
import {
  Card,
  CardHeader,
  CardTitle,
  CardContent,
  CardDescription,
} from "@/components/ui/card";
import {
  usePlatformSchedules,
  usePlatformMutations,
  useScheduleFires,
  usePackages,
} from "@/hooks/use-workflow-platform";
import { scheduleFireLabel } from "@/lib/schedule-frequency";
import { scheduleSummary } from "@/lib/schedule-frequency";
import type { Schedule } from "@/lib/types/workflow-platform";
import { AppliedSchedulePreview } from "./schedule-timing";
import { RequestError } from "./feedback";

function ScheduleRow({
  schedule: s,
  taskName,
}: {
  schedule: Schedule;
  taskName: string;
}) {
  const mutations = usePlatformMutations();
  const fires = useScheduleFires(s.id);
  const latest = fires.data?.items
    .slice()
    .sort((a, b) => b.scheduledAt.localeCompare(a.scheduledAt))[0];
  const [triggerId, setTriggerId] = useState(() => scheduleTriggerDrafts.get(s.id) ?? crypto.randomUUID());
  const [triggerUncertain, setTriggerUncertain] = useState(scheduleTriggerDrafts.has(s.id));
  useUnsavedWork(triggerUncertain);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState<unknown>(null);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{s.name}</CardTitle>
        <CardDescription>
          {taskName} · {s.syncStatus === "synced" ? s.paused ? "已暂停" : "已启用自动执行" : s.paused ? "暂停尚未确认" : "启用尚未确认"} ·{" "}
          {s.syncStatus === "synced"
            ? "已生效"
            : s.syncStatus === "failed"
              ? "修改未能生效"
              : "正在应用修改"}
          {s.desiredDeleted ? " · 正在删除" : ""}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <p className="text-sm">
          {scheduleSummary(s.cron)} · {s.timeZone}
        </p>
        {s.syncErrorCode && (
          <p className="text-sm text-destructive">
            修改未能生效，之前的安排可能仍在执行。请打开安排核对设置后再次保存，系统也会继续尝试。
          </p>
        )}
        <AppliedSchedulePreview id={s.id} revision={s.revision} syncStatus={s.syncStatus} />
        <p className="text-sm">
          最近执行：{" "}
          {latest ? (
            latest.runId ? (
              <Link
                className="underline"
                to={`/runs/${encodeURIComponent(latest.runId)}`}
              >
                {scheduleFireLabel(latest.status)} ·{" "}
                {new Date(latest.scheduledAt).toLocaleString()}
              </Link>
            ) : (
              `${scheduleFireLabel(latest.status)} — 尚未生成结果`
            )
          ) : fires.isError ? (
            "暂时无法读取历史"
          ) : (
            "暂无记录"
          )}
        </p>
        <RequestError error={error} />
        {triggerUncertain && <p role="alert" className="text-sm">执行请求尚未确认，任务可能已经开始。请点击“确认执行请求”核对，避免重复执行。</p>}
        {notice && (
          <p role="status" className="text-sm">
            {notice}
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button asChild variant="outline">
            <Link to={`/scheduled-tasks/${encodeURIComponent(s.id)}`}>
              查看 {s.name}
            </Link>
          </Button>
          <Button
            variant="outline"
            disabled={s.desiredDeleted || triggerUncertain || mutations.saveSchedule.isPending}
            onClick={() => {
              mutations.saveSchedule
                .mutateAsync({ ...s, paused: !s.paused })
                .then((saved) => {
                  setError(null);
                  setNotice(
                    saved.syncStatus !== "synced" ? "修改已保存，正在确认是否生效。请查看上方状态。" : saved.paused
                      ? "已暂停未来自动执行，当前任务继续运行。"
                      : "已恢复未来自动执行。",
                  );
                })
                .catch(setError);
            }}
          >
            {s.paused ? "恢复" : "暂停"}
          </Button>
          <Button
            variant="outline"
            disabled={s.desiredDeleted || mutations.triggerSchedule.isPending}
            onClick={() => {
              scheduleTriggerDrafts.set(s.id, triggerId);
              setTriggerUncertain(true);
              mutations.triggerSchedule
                .mutateAsync({ id: s.id, triggerId })
                .then((receipt) => {
                  if (receipt.status !== "accepted")
                    throw new Error("请求尚未确认，请使用同一请求重试。");
                  setError(null);
                  setNotice("已请求执行，打开安排可跟进结果。");
                  setTriggerUncertain(false);
                  scheduleTriggerDrafts.delete(s.id);
                  setTriggerId(crypto.randomUUID());
                })
                .catch(error => {
                  if (error instanceof ApiRequestError && [400, 404, 422].includes(error.status)) {
                    setTriggerUncertain(false);
                    scheduleTriggerDrafts.delete(s.id);
                  }
                  setError(error);
                });
            }}
          >
            {triggerUncertain ? "确认执行请求" : "立即执行"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
export function SchedulesPage() {
  const schedules = usePlatformSchedules();
  const packages = usePackages();
  return (
    <InventoryPageShell
      pageContext={{
        title: "自动执行",
        description: "沿用业务信息，在固定时区重复执行任务",
        actions: (
          <Button asChild>
            <Link to="/scheduled-tasks/new">安排重复执行</Link>
          </Button>
        ),
      }}
    >
      <div className="flex flex-col gap-3">
        <RequestError
          error={schedules.error}
          retry={() => void schedules.refetch()}
        />
        {schedules.isPending && <InventoryStatePanel title="正在读取安排…" />}
        {schedules.data?.items.length === 0 && (
          <InventoryStatePanel
            title="暂无自动执行安排"
            description="选择任务，准备好业务信息后启用重复执行。"
          />
        )}
        {schedules.data?.items.map((s) => (
          <ScheduleRow
            key={s.id}
            schedule={s}
            taskName={
              packages.data?.items.find((p) => p.key === s.packageKey)
                ?.definition.workflows[s.workflowKey]?.name ||
              s.name
            }
          />
        ))}
      </div>
    </InventoryPageShell>
  );
}
