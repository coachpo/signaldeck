export const resultStatusLabels: Record<string, string> = {
  queued: "等待开始",
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
  schedule: "自动执行",
};
