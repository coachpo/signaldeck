import type { ResourceStatusTone } from "@/components/shared/resource-status-strip";

export const resultStatusLabels: Record<string, string> = {
  queued: "等待开始",
  pending: "等待开始",
  running: "正在执行",
  succeeded: "已完成",
  failed: "执行失败",
  cancelled: "已取消",
  unknown: "保存状态待核实",
  blocked: "未执行：前置条件未满足",
  skipped: "已跳过",
  timed_out: "执行超时",
};
export const originLabels: Record<string, string> = {
  manual: "手动开始",
  rerun: "再运行一次",
  reuse: "调整后开始",
  schedule: "自动执行",
};
export const contentStatusLabels: Record<string, string> = {
  not_available: "尚无确认内容", available: "内容已确认", partial: "部分内容已确认", unknown: "保存状态待核实",
};

export function resultStatusTone(status?: string): ResourceStatusTone {
  switch (status) {
    case "failed":
    case "timed_out":
      return "danger";
    case "unknown":
    case "blocked":
      return "warning";
    case "succeeded":
      return "success";
    case "cancelled":
    case "skipped":
      return "muted";
    default:
      return "neutral";
  }
}
