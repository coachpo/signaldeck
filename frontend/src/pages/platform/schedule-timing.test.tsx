import { useState } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, expect, it, vi } from "vitest";
import { ScheduleTiming } from "./schedule-timing";
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
function Form() {
  const [draft, setDraft] = useState(initial);
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
