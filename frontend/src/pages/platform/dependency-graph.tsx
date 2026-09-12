import { resultStatusTone } from "./result-labels";
import { useRef, useState } from "react";
import { ChoiceField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { ResourceStatusBadge } from "@/components/shared/resource-status-strip";
import type {
  ExecutionEvidence,
  WorkflowPlan,
} from "@/lib/types/workflow-platform";
export function DependencyGraph({
  plan,
  evidence,
  onSelect,
  name = "步骤关系",
  nodeLabels = {},
}: {
  plan: WorkflowPlan;
  name?: string;
  nodeLabels?: Record<string, string>;
  evidence?: ExecutionEvidence[];
  onSelect?: (nodeId: string, evidenceId?: string) => void;
}) {
  const labelFor = (key: string) => nodeLabels[key] ?? `步骤 ${plan.nodeOrder.indexOf(key) + 1}`;
  const edgeLabels = { control: "等待完成", input: "使用结果", condition: "根据结果判断" };
  const statusLabels: Record<string, string> = { pending: "等待开始", running: "进行中", succeeded: "已完成", failed: "未能完成", blocked: "前置步骤未完成", skipped: "条件不满足，已跳过", cancelled: "已取消", unknown: "结果尚未确认", timed_out: "等待超时" };
  const [zoom, setZoom] = useState(1);
  const [located, setLocated] = useState("");
  const viewport = useRef<HTMLDivElement>(null);
  const drag = useRef<{
    x: number;
    y: number;
    left: number;
    top: number;
  } | null>(null);
  const levels = new Map<string, number>();
  for (const key of plan.nodeOrder)
    levels.set(
      key,
      Math.max(
        0,
        ...(plan.dependencies[key] ?? []).map(
          (dep) => (levels.get(dep) ?? 0) + 1,
        ),
      ),
    );
  const columns = Array.from(new Set(levels.values()));
  const positions = new Map<string, { x: number; y: number }>();
  for (const level of columns) {
    plan.nodeOrder
      .filter((key) => levels.get(key) === level)
      .forEach((key, index) =>
        positions.set(key, { x: 24 + level * 240, y: 24 + index * 140 }),
      );
  }
  const width = Math.max(440, columns.length * 240);
  const height = Math.max(
    300,
    ...[...positions.values()].map((p) => p.y + 140),
  );
  function reset() {
    setZoom(
      Math.min(
        1,
        Math.max(0.25, (viewport.current?.clientWidth || width) / width),
      ),
    );
    if (viewport.current) {
      viewport.current.scrollLeft = 0;
      viewport.current.scrollTop = 0;
    }
  }
  return (
    <Card>
      <CardHeader>
        <CardTitle>{name}</CardTitle>
        <CardDescription>
          连线说明步骤为什么需要等待；选择步骤可查看或调整。
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <div
          className="flex flex-wrap items-center gap-2"
          aria-label="图视口工具"
        >
          <Button variant="outline" onClick={reset}>
            自动布局 / 适合窗口
          </Button>
          <Button
            variant="outline"
            aria-label="缩小图"
            disabled={zoom <= 0.25}
            onClick={() => setZoom((v) => Math.max(0.25, v - 0.25))}
          >
            −
          </Button>
          <output aria-label="图缩放">{Math.round(zoom * 100)}%</output>
          <Button
            variant="outline"
            aria-label="放大图"
            disabled={zoom >= 2}
            onClick={() => setZoom((v) => Math.min(2, v + 0.25))}
          >
            +
          </Button>
          <ChoiceField
            label="定位步骤"
            value={located}
            options={plan.nodeOrder.map((key) => ({ value: key, label: labelFor(key) }))}
            onChange={(key) => {
              setLocated(key);
              const position = positions.get(key);
              if (position && viewport.current) {
                viewport.current.scrollLeft = Math.max(
                  0,
                  position.x * zoom - viewport.current.clientWidth / 3,
                );
                viewport.current.scrollTop = Math.max(
                  0,
                  position.y * zoom - 80,
                );
              }
              viewport.current
                ?.querySelector<HTMLButtonElement>(
                  `[data-node-index="${plan.nodeOrder.indexOf(key)}"]`,
                )
                ?.focus({ preventScroll: true });
            }}
          />
          <span className="text-xs text-muted-foreground">
            拖动空白处或滚动平移；方向键移动视口。
          </span>
        </div>
        <div
          ref={viewport}
          className="max-h-96 overflow-auto rounded border border-border bg-ui-surface-inset"
          aria-label="任务步骤"
          role="region"
          tabIndex={0}
          onPointerDown={(e) => {
            if ((e.target as HTMLElement).closest("button")) return;
            e.preventDefault();
            drag.current = {
              x: e.clientX,
              y: e.clientY,
              left: e.currentTarget.scrollLeft,
              top: e.currentTarget.scrollTop,
            };
            e.currentTarget.setPointerCapture?.(e.pointerId);
          }}
          onPointerMove={(e) => {
            if (drag.current) {
              e.currentTarget.scrollLeft =
                drag.current.left + drag.current.x - e.clientX;
              e.currentTarget.scrollTop =
                drag.current.top + drag.current.y - e.clientY;
            }
          }}
          onPointerUp={() => {
            drag.current = null;
          }}
          onPointerCancel={() => {
            drag.current = null;
          }}
          onKeyDown={(e) => {
            if (e.target !== e.currentTarget) return;
            const moves: Record<string, [number, number]> = {
              ArrowLeft: [-60, 0],
              ArrowRight: [60, 0],
              ArrowUp: [0, -60],
              ArrowDown: [0, 60],
            };
            const move = moves[e.key];
            if (move) {
              e.preventDefault();
              e.currentTarget.scrollLeft += move[0];
              e.currentTarget.scrollTop += move[1];
            }
          }}
        >
          <div style={{ width: width * zoom, height: height * zoom }}>
            <div
              className="relative origin-top-left"
              style={{ width, height, transform: `scale(${zoom})` }}
            >
              <svg
                width={width}
                height={height}
                className="absolute inset-0 text-muted-foreground"
                aria-hidden="true"
              >
                {plan.edges.map((edge) => {
                  const from = positions.get(edge.source),
                    to = positions.get(edge.target);
                  if (!from || !to) return null;
                  return (
                    <g key={`${edge.source}:${edge.target}`}>
                      <path
                        d={`M ${from.x + 184} ${from.y + 45} C ${from.x + 212} ${from.y + 45}, ${to.x - 28} ${to.y + 45}, ${to.x} ${to.y + 45}`}
                        fill="none"
                        stroke="currentColor"
                      />
                      <path
                        d={`M ${to.x - 6} ${to.y + 41} L ${to.x} ${to.y + 45} L ${to.x - 6} ${to.y + 49}`}
                        fill="none"
                        stroke="currentColor"
                      />
                      <title>
                        {labelFor(edge.source)} → {labelFor(edge.target)}: {edge.sources.map((source) => edgeLabels[source]).join("、")}
                      </title>
                    </g>
                  );
                })}
              </svg>
              {plan.nodeOrder.map((key, index) => {
                const position = positions.get(key)!;
                const node = (evidence ?? [])
                  .filter((e) => e.nodeId === key && e.kind === "node")
                  .sort((a, b) => b.attempt - a.attempt)[0];
                return (
                  <div
                    key={key}
                    className="absolute flex w-46 flex-col gap-2 rounded border border-border bg-ui-surface-grouped p-3"
                    style={{ left: position.x, top: position.y }}
                  >
                    <Button
                      variant="outline"
                      data-node-index={index}
                      className="justify-start overflow-hidden"
                      onClick={() => onSelect?.(key, node?.id)}
                    >
                      {labelFor(key)}
                    </Button>
                    <ResourceStatusBadge
                      label={
                        node ? statusLabels[node.status] : evidence ? "尚未开始" : "已安排"
                      }
                      tone={resultStatusTone(node?.status)}
                    />

                  </div>
                );
              })}
            </div>
          </div>
        </div>
        <ul
          aria-label="步骤之间的关系"
          className="flex flex-col gap-2 text-sm"
        >
          {plan.edges.map((edge) => (
            <li
              key={`${edge.source}:${edge.target}`}
              className="flex flex-wrap items-center gap-2"
            >
              <span>
                {labelFor(edge.source)} → {labelFor(edge.target)}
              </span>
              {edge.sources.map((source) => (
                <ResourceStatusBadge key={source} label={edgeLabels[source]} />
              ))}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
