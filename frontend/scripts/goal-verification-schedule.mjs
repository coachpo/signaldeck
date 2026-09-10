import assert from "node:assert/strict";
import { writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { chromium, expect } from "@playwright/test";

const args = Object.fromEntries(process.argv.slice(2).reduce((rows, item, index, all) => {
  if (index % 2 === 0) rows.push([item.replace(/^--/, ""), all[index + 1]]);
  return rows;
}, []));
for (const key of ["base-url", "schedule-id", "output", "fire-at"]) assert(args[key], key);
assert(["127.0.0.1", "localhost"].includes(new URL(args["base-url"]).hostname));
const evidence = { scheduleId: args["schedule-id"], openedAt: new Date().toISOString(), browserClosed: false };
const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.goto(new URL(`/scheduled-tasks/${encodeURIComponent(args["schedule-id"])}`, args["base-url"]).href);
  await expect(page.getByText("安排已生效", { exact: true })).toBeVisible({ timeout: 15000 });
  evidence.pageUrl = page.url();
  evidence.savedScheduleObserved = true;
} finally {
  await browser.close();
  evidence.browserClosed = true;
  evidence.closedAt = new Date().toISOString();
  await writeFile(resolve(args.output, "schedule-browser.json"), `${JSON.stringify(evidence, null, 2)}\n`);
}
assert(Date.parse(evidence.closedAt) < Date.parse(args["fire-at"]), "Browser must close before the planned natural fire");
