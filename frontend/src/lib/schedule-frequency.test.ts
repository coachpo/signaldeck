import { describe, expect, it } from "vitest";
import {
  decodeFrequency,
  encodeFrequency,
  scheduleSummary,
} from "./schedule-frequency";
describe("schedule frequency codec", () => {
  it.each(["0 9 * * *", "30 23 * * 0", "59 0 31 * *"])(
    "preserves %s",
    (cron) => {
      const decoded = decodeFrequency(cron);
      expect(decoded).not.toBeNull();
      expect(encodeFrequency(decoded!)).toBe(cron);
    },
  );
  it.each([
    "0 9 1 * 1",
    "*/5 * * * *",
    "0 9 * 1 *",
    "60 9 * * *",
    "0 24 * * *",
    "0 9 0 * *",
    "0 9 * * 7",
  ])("retains unsupported timing %s", (cron) => {
    expect(decodeFrequency(cron)).toBeNull();
    expect(scheduleSummary(cron)).toContain(cron);
  });
  it("describes weekly timing without calculating dates", () => {
    expect(scheduleSummary("30 9 * * 1")).toBe("每周一 09:30");
  });
});
