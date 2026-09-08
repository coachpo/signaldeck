"""Render paired measurements without treating ablated failures as product success."""

from __future__ import annotations

import argparse
import json
import statistics
from collections import defaultdict
from pathlib import Path

LABELS = {
    "cache_repeated": "缓存：重复输入",
    "cache_unique": "缓存：唯一输入",
    "retry_healthy": "重试：正常响应",
    "retry_transient": "重试：首次瞬态失败",
    "retry_persistent": "重试：持续失败",
    "limiter_within_capacity": "限流：1 个请求",
    "limiter_burst": "限流：8 个并发请求",
    "ownership_normal": "独占：单次写入",
    "ownership_overlap": "独占：重叠投递",
    "dag_branches": "DAG：4 分支及汇合",
    "dag_chain": "DAG：4 节点链",
}
METRICS = {
    "successes": "成功数",
    "tool_calls": "执行调用",
    "calls": "执行调用",
    "release_checks": "发布核验",
    "cache_hits": "缓存命中",
    "peak_active": "并发峰值",
    "capacity_rejections": "容量拒绝",
    "effects": "写入效果数",
    "queries": "写效果查询",
}


def spread(values, precision=1):
    middle = statistics.median(values)
    low, high = min(values), max(values)
    return f"{middle:.{precision}f} [{low:.{precision}f}, {high:.{precision}f}]"


def render(data):
    if data.get("source_drift"):
        raise ValueError("Source changed during measurement; repeat against a stable source tree")
    if data["exit_status"] != 0 or any(row["outcome"] != "passed" for row in data["outcomes"]):
        raise ValueError("Experiment contains failed or skipped checks; inspect raw outcomes first")
    groups = defaultdict(dict)
    for row in data["measurements"]:
        key = (row["variant"], row["sample"])
        if key in groups[row["scenario"]]:
            raise ValueError("Duplicate scenario/variant/sample")
        groups[row["scenario"]][key] = row["metrics"]
    expected = {(variant, i) for variant in ("baseline", "ablated") for i in range(data["samples"])}
    if set(groups) != set(LABELS) or any(set(rows) != expected for rows in groups.values()):
        raise ValueError("A complete report requires every workload and matched baseline/ablation")
    lines = [
        "# SignalDeck 后端机制消融实验",
        "",
        f"源码基线：`{data['revision']}`；完成时间：{data['completed_at']}。",
        f"每个场景、每个变体重复 {data['samples']} 次，共 {len(data['measurements'])} 次测量。",
        "所有实验断言通过表示观察到了预设对照结果，包含消融后预期出现的失败或重复效果。",
        "",
        "## 方法及边界",
        "",
        "每次只关闭一个机制；配对样本交替先后顺序，各自创建独立 PostgreSQL 临时库。",
        "DAG 使用真实本地 Temporal、Core Worker 和进程内 MCP ASGI 传输；其他组使用真实",
        "ToolGateway/PostgreSQL 加受控传输。无真实模型、收费 API 或业务写入。",
        "耗时排除数据库、Temporal、Worker 初始化，包含各实验声明的业务路径及证据持久化。",
        "没有额外预热；给出中位数及 [最小值, 最大值]，不推断统计显著性或生产性能。",
        "限流组含首批调用同步屏障，耗时仅作描述；容量拒绝基于假定的两槽服务。",
        "缓存执行延迟设为 40ms、发布核验 5ms；DAG 工具延迟 350ms。缓存命中仍核验发布。",
        "独占组是两个独立存储适配器的重叠调用，未模拟两个操作系统 Worker 崩溃。",
        "本轮不消融整个 Temporal、固定制品、取消、调度、前端或 Agent 输出质量。",
        "",
        f"运行环境：Python {data['python'].split()[0]}，{data['platform']}。",
        "依赖："
        + "，".join(f"{key} {value}" for key, value in data["dependencies"].items())
        + "。",
        "",
        "## 耗时（ms）",
        "",
        "配对变化为各样本 `(消融 / 基线 - 1) × 100%` 的中位数；正值表示消融后更慢。",
        "",
        "| 场景 | 基线中位数 [范围] | 消融中位数 [范围] | 配对变化 |",
        "| --- | ---: | ---: | ---: |",
    ]
    for scenario, label in LABELS.items():
        rows = groups[scenario]
        base = [rows["baseline", i]["elapsed_ms"] for i in range(data["samples"])]
        removed = [rows["ablated", i]["elapsed_ms"] for i in range(data["samples"])]
        delta = statistics.median((a / b - 1) * 100 for a, b in zip(removed, base, strict=True))
        lines.append(f"| {label} | {spread(base)} | {spread(removed)} | {delta:+.1f}% |")
    lines += [
        "",
        "## 可观察行为",
        "",
        "数值同样显示每次工作负载的中位数及范围；成功数的分母见实验配置。",
        "",
        "| 场景 | 指标 | 基线 | 消融 |",
        "| --- | --- | ---: | ---: |",
    ]
    for scenario, label in LABELS.items():
        rows = groups[scenario]
        for metric, description in METRICS.items():
            if metric not in rows["baseline", 0]:
                continue
            baseline = [rows["baseline", i][metric] for i in range(data["samples"])]
            ablated = [rows["ablated", i][metric] for i in range(data["samples"])]
            lines.append(
                f"| {label} | {description} | {spread(baseline, 0)} | {spread(ablated, 0)} |"
            )
    lines += [
        "",
        "完整样本、各阶段检查结果、版本、源文件 SHA-256 清单见同目录 `metrics.json`。",
        "消融开关、控制条件及复现入口见 `backend/experiments/ablation/README.md`。",
        "",
    ]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text(render(json.loads(args.input.read_text())))
    print(args.output.resolve())


if __name__ == "__main__":
    main()
