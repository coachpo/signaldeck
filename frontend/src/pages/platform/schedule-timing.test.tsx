import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { ScheduleTiming, AppliedSchedulePreview } from "./schedule-timing";
import type { ScheduleConfig } from "@/lib/types/workflow-platform";
afterEach(() => vi.unstubAllGlobals());
const initial: ScheduleConfig = {
  name: "Daily",
  packageKey: "saved",
  workflowKey: "work",
  parameters: { message: "keep" },
  cron: "0 8,17 * * 1-5",
  timeZone: "Europe/Helsinki",
  overlapPolicy: "buffer_one",
  catchupWindowSeconds: 180,
  paused: true,
};
function Form({ cron }: { cron?: string } = {}) {
  const [draft, setDraft] = useState(cron ? { ...initial, cron } : initial);
  return (
    <QueryClientProvider
      client={
        new QueryClient({ defaultOptions: { queries: { retry: false } } })
      }
    >
      <ScheduleTiming draft={draft} onChange={setDraft} />
      <output aria-label="Saved draft">{JSON.stringify(draft)}</output>
    </QueryClientProvider>
  );
}
it("preserves complex calendar and hidden policies while editing the timezone", () => {
  render(<Form />);
  fireEvent.change(screen.getByRole("combobox", { name: "时区" }), {
    target: { value: "America/New_York" },
  });
  expect(JSON.parse(screen.getByLabelText("Saved draft").textContent!)).toEqual(
    { ...initial, timeZone: "America/New_York" },
  );
});
it("marks an unavailable engine preview without changing the schedule", async () => {
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("offline")));
  render(<Form />);
  fireEvent.click(screen.getByRole("button", { name: "预览下次时间" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "没有启用自动执行",
  );
  expect(JSON.parse(screen.getByLabelText("Saved draft").textContent!)).toEqual(
    initial,
  );
});
it("edits multiple execution hours without exposing an expression editor", () => {
  render(<Form />);
  expect(screen.queryByLabelText("自定义时间表达式")).not.toBeInTheDocument();
  expect(screen.getByRole("checkbox", { name: "执行小时 8时" })).toBeChecked();
  expect(screen.getByRole("checkbox", { name: "执行小时 17时" })).toBeChecked();
  fireEvent.click(screen.getByRole("checkbox", { name: "执行小时 9时" }));
  const changed = JSON.parse(screen.getByLabelText("Saved draft").textContent!);
  expect(changed).toEqual({ ...initial, cron: "0 8-9,17 * * 1-5" });
});
it("shows authoritative pending preview without internal revisions or notes", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(JSON.stringify({
    scope: "applied", paused: false, timeZone: "Europe/Helsinki", times: ["2026-09-15T06:00:00Z"],
    observedAt: "2026-09-12T08:00:00Z", desiredRevision: 7, syncedRevision: 6,
    appliedNote: "SignalDeck revision 6",
  }))));
  render(<QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
    <AppliedSchedulePreview id="internal-schedule" revision={7} syncStatus="pending" />
  </QueryClientProvider>);
  expect(await screen.findByText(/修改尚未生效/)).toBeVisible();
  expect(screen.getByText(/之前的执行时间/)).toBeVisible();
  expect(screen.queryByText(/SignalDeck|revision|internal-schedule|调度服务|版本/)).not.toBeInTheDocument();
  expect(screen.getByText(/9:00/)).toBeVisible();
});

it("edits a fixed interval and its reference time through ordinary controls", () => {
  render(<Form cron="@every 14h/3h" />);
  expect(screen.getByRole("spinbutton", { name: "每隔" })).toHaveValue(14);
  fireEvent.change(screen.getByLabelText("参考起点（协调世界时）"), { target: { value: "2026-09-12T03:00:05" } });
  fireEvent.change(screen.getByRole("spinbutton", { name: "每隔" }), { target: { value: "24" } });
  const changed = JSON.parse(screen.getByLabelText("Saved draft").textContent!);
  expect(changed.cron).toBe("@every 86400s/10805s");
  expect(changed.parameters).toEqual(initial.parameters);
  expect(screen.queryByLabelText("自定义时间表达式")).not.toBeInTheDocument();
});
