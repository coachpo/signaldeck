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
}: {
  plan: WorkflowPlan;
  evidence?: ExecutionEvidence[];
  onSelect?: (nodeId: string, evidenceId?: string) => void;
}) {
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
        <CardTitle>Workflow graph</CardTitle>
        <CardDescription>
          {plan.workflowKey} · dependency readiness and edge sources
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
            label="定位节点"
            value={located}
            options={plan.nodeOrder.map((key) => ({ value: key, label: key }))}
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
          aria-label="Workflow nodes"
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
                        {edge.source} → {edge.target}: {edge.sources.join(", ")}
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
                      {key}
                    </Button>
                    <ResourceStatusBadge
                      label={
                        node?.status ?? (evidence ? "no evidence" : "defined")
                      }
                      tone={node?.status === "failed" ? "danger" : "neutral"}
                    />
                    {node?.errorCode && (
                      <span className="break-all text-xs text-destructive">
                        {node.errorCode}
                      </span>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
        <ul
          aria-label="Dependency edges"
          className="flex flex-col gap-2 text-sm"
        >
          {plan.edges.map((edge) => (
            <li
              key={`${edge.source}:${edge.target}`}
              className="flex flex-wrap items-center gap-2"
            >
              <span>
                {edge.source} → {edge.target}
              </span>
              {edge.sources.map((source) => (
                <ResourceStatusBadge key={source} label={source} />
              ))}
              <span className="break-all text-xs text-muted-foreground">
                {edge.paths.join(", ")}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
