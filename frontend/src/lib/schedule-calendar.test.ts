import { describe, expect, it } from "vitest";
import { decodeCalendar, encodeCalendar, decodeInterval, encodeInterval } from "./schedule-calendar";

describe("calendar controls preserve existing timing", () => {
  it.each([
    "0 8,17 * * 1-5", "0 9 1,15 JAN-MAR/2 MON,FRIDAY 2026-2032/2",
    "5,35 */10 8-17/3 1-20/2,25 JUL 1-7/2 2027", "@weekly", "@annually",
    "  00 09 * * 7  # Keep the user's note", "* * * * * * *", "0 0 * * tu-sa",
  ])("round-trips %s without replacing untouched source", source => {
    const calendar = decodeCalendar(source);
    expect(calendar).not.toBeNull();
    expect(encodeCalendar(calendar!)).toBe(source);
  });
  it("changes one selection while preserving other supported dimensions and notes", () => {
    const calendar = decodeCalendar("5,35 */10 8-17/3 1-20/2,25 JUL 1-7/2 2027 # report dates")!;
    const edited = encodeCalendar({ ...calendar, values: { ...calendar.values, hour: [8, 17] } });
    expect(edited).toBe("5,35 */10 8,17 1-20/2,25 JUL 1-7/2 2027 # report dates");
    expect(decodeCalendar(edited)?.values).toEqual({ ...calendar.values, hour: [8, 17] });
  });
  it("adds seconds and year controls without losing the five-field calendar", () => {
    const calendar = decodeCalendar("30 9 1 * 1")!;
    const edited = encodeCalendar({ ...calendar, values: { ...calendar.values, second: [5, 35], year: [2026, 2028, 2030] } });
    expect(edited).toBe("5,35 30 9 1 * 1 2026-2030/2");
    expect(decodeCalendar(edited)?.values.weekday).toEqual([1]);
    expect(decodeCalendar(edited)?.values.day).toEqual([1]);
  });
  it.each(["60 9 * * *", "0 24 * * *", "0 9 0 * *", "0 9 * * 8", "*/0 * * * *", "0 9 * * * 1999", "0 9 * * * * * *"])("does not reinterpret invalid timing %s", source => {
    expect(decodeCalendar(source)).toBeNull();
  });
});
describe("fixed interval controls", () => {
  it.each(["@every 1h30m", "@every 14h/3h", "@every 2d/30m # recurring", "@every 500ms500ms"])("preserves %s", source => {
    const interval = decodeInterval(source);
    expect(interval).not.toBeNull();
    expect(encodeInterval(interval!)).toBe(source);
  });
  it("retains the reference start when changing the interval", () => {
    const interval = decodeInterval("@every 14h/3h # recurring")!;
    const edited = encodeInterval({ ...interval, seconds: 86400 });
    expect(decodeInterval(edited)).toMatchObject({ seconds: 86400, phase: 10800 });
    expect(edited).toContain("# recurring");
  });
});
