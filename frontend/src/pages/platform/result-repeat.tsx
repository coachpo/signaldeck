import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Button } from "@/components/ui/button";
import { useResultRerun, usePendingResultRerun } from "@/hooks/use-results";
import { ApiRequestError } from "@/lib/api-client";
import { useTaskMutations } from "@/hooks/use-task-experience";
import type { RunResult } from "@/lib/types/result";
import type { ReuseInput } from "@/lib/types/task-experience";
import { TaskPreparation } from "./task-preparation";
import { RequestError } from "./feedback";
export function ResultRepeat({
  result,
  original,
}: {
  result: RunResult;
  original?: ReuseInput;
}) {
  const command = usePendingResultRerun(result.runId);
  const [launchId] = useState(() => command.pending?.launchId ?? crypto.randomUUID());
  const [showRepeat, setShowRepeat] = useState(false);
  const [unknownChecked, setUnknownChecked] = useState(!!command.pending);
  const task = useTaskMutations();
  const rerun = useResultRerun();
  const navigate = useNavigate();
  const preparation = command.pending?.preparation ?? task.prepare.data;
  async function prepare() {
    if (!original) return;
    setShowRepeat(true);
    if (command.pending) return;
    await task.prepare
      .mutateAsync({
        packageKey: original.packageKey,
        workflowKey: original.workflowKey,
        parameters: original.parameters,
        revisionHash: original.packageHash,
        sourceRunId: result.runId,
      })
      .catch(() => {});
  }
  async function start() {
    if (!preparation?.bindingToken) return;
    command.retain({ launchId, preparation });
    try {
      const next = await rerun.mutateAsync({
        id: result.runId,
        launchId,
        bindingToken: preparation.bindingToken,
      });
      command.clear();
      navigate(`/runs/${encodeURIComponent(next.id)}`);
    } catch (error) {
      if (error instanceof ApiRequestError && error.status >= 400 && error.status < 500) {
        command.clear();
        task.prepare.reset();
      }
    }
  }
  return (
    <>
      <Button
        disabled={!original || task.prepare.isPending}
        onClick={() => void prepare()}
      >
        再运行一次
      </Button>
      <RequestError error={task.prepare.error || rerun.error} />
      {showRepeat && preparation && (
        <section className="basis-full flex flex-col gap-3 rounded border border-border bg-card p-4">
          <h2 className="font-semibold">确认再运行</h2>
          <p className="text-sm">
            沿用原任务版本和输入，创建独立结果；使用当前连接。原结果不会改变。
          </p>
          {command.pending && (
            <p role="status" className="text-sm">
              上次请求尚未确认。继续操作会重试同一请求与已确认的连接设置，避免重复执行。
            </p>
          )}
          <TaskPreparation preparation={preparation} />
          {!preparation.ready && (
            <Button asChild variant="outline">
              <Link
                to={`/tasks/new?fromRun=${encodeURIComponent(result.runId)}`}
              >
                保留输入并修复连接
              </Link>
            </Button>
          )}
          {result.contentStatus === "unknown" && (
            <label className="flex items-start gap-2 text-sm">
              <input
                type="checkbox"
                checked={unknownChecked}
                onChange={(e) => setUnknownChecked(e.target.checked)}
              />
              我已核实目标位置与执行证据，确认需要再次执行
            </label>
          )}
          <Button
            disabled={
              !preparation.ready ||
              !preparation.bindingToken ||
              rerun.isPending ||
              (result.contentStatus === "unknown" && !unknownChecked)
            }
            onClick={() => void start()}
          >
            确认并开始新运行
          </Button>
        </section>
      )}
    </>
  );
}
