import { expect, test, type APIRequestContext } from "@playwright/test";
import { apiBase } from "./platform-fixtures";
import { connectTaskServices } from "./task-fixtures";

// Select a real timezone whose local calendar day differs from UTC. This exposes
// date-only filters accidentally interpreted as UTC without changing stored runs.
const timezoneId =
  new Date().getUTCHours() >= 10 ? "Pacific/Kiritimati" : "Pacific/Pago_Pago";
test.use({ timezoneId });

async function capture(request: APIRequestContext, title: string) {
  const parameters = { title, text: `Immutable original for ${title}` };
  const prepared = await request.post(
    `${apiBase}/workflow-packages/research_notes/prepare`,
    { data: { workflowKey: "capture", parameters } },
  );
  expect(prepared.ok(), await prepared.text()).toBeTruthy();
  const preparation = await prepared.json();
  expect(preparation.ready).toBe(true);
  const launched = await request.post(
    `${apiBase}/workflow-packages/research_notes/launches`,
    {
      data: {
        workflowKey: "capture",
        parameters,
        launchId: crypto.randomUUID(),
        bindingToken: preparation.bindingToken,
      },
    },
  );
  expect(launched.ok(), await launched.text()).toBeTruthy();
  return launched.json();
}

test("UX03: complete history preserves filters, respects local dates and refreshes the snapshot", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(240_000);
  await connectTaskServices(request, false);
  const prefix = `history-${crypto.randomUUID().slice(0, 8)}`;
  const runs = [];
  for (let i = 0; i < 27; i++)
    runs.push(
      await capture(request, `${prefix} ${String(i).padStart(2, "0")}`),
    );
  await expect
    .poll(
      async () => {
        const response = await request.get(
          `${apiBase}/runs?q=${prefix}&status=succeeded&limit=100`,
        );
        return (await response.json()).total;
      },
      { timeout: 120_000 },
    )
    .toBe(27);
  await page.goto(`/runs?q=${prefix}&sort=title_asc`);
  await expect(page.getByText("共 27 条记录", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", { name: `${prefix} 00`, exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "下一页", exact: true }).click();
  await expect(
    page.getByRole("link", { name: `${prefix} 26`, exact: true }),
  ).toBeVisible();
  const secondPage = page.url();
  expect(new URL(secondPage).searchParams.get("snapshotAt")).toBeTruthy();
  await page.getByRole("link", { name: `${prefix} 26`, exact: true }).click();
  await expect(
    page.getByRole("heading", { name: `${prefix} 26`, exact: true }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "技术详情与调用证据", exact: true })
    .click();
  await page
    .getByRole("tab", { name: "Immutable snapshot", exact: true })
    .click();
  await page.getByRole("link", { name: "返回结果", exact: true }).click();
  await page.getByRole("link", { name: "全部结果", exact: true }).click();
  await expect(page).toHaveURL(secondPage);
  await expect(
    page.getByRole("link", { name: `${prefix} 26`, exact: true }),
  ).toBeVisible();

  const fresh = await capture(request, `${prefix} 00-new`);
  await page.getByRole("button", { name: "刷新", exact: true }).click();
  await expect(page.getByText("共 28 条记录", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("link", { name: `${prefix} 00-new`, exact: true }),
  ).toBeVisible();
  expect(new URL(page.url()).searchParams.has("offset")).toBe(false);
  expect(new URL(page.url()).searchParams.has("snapshotAt")).toBe(false);

  const dates = await page.evaluate((createdAt) => {
    const date = new Date(createdAt);
    const day = (d: Date) =>
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    const local = day(date);
    const previous = new Date(date);
    previous.setDate(previous.getDate() - 1);
    return {
      local,
      previous: day(previous),
      utc: date.toISOString().slice(0, 10),
    };
  }, fresh.createdAt);
  expect(dates.local).not.toBe(dates.utc);
  await page.getByLabel("起始日期", { exact: true }).fill(dates.local);
  const filteredResponse = page.waitForResponse((response) => {
    const url = new URL(response.url());
    return (
      url.pathname === "/api/runs" &&
      url.searchParams.has("createdFrom") &&
      url.searchParams.has("createdTo")
    );
  });
  await page.getByLabel("结束日期", { exact: true }).fill(dates.local);
  const filtered = await filteredResponse;
  expect(filtered.ok()).toBeTruthy();
  expect((await filtered.json()).total).toBe(28);
  await expect(
    page.getByRole("link", { name: `${prefix} 00-new`, exact: true }),
  ).toBeVisible();
  await expect(page.getByText("共 28 条记录", { exact: true })).toBeVisible();
  const filteredUrl = page.url();
  expect(new URL(filteredUrl).searchParams.get("createdFrom")).toMatch(/Z$/);
  expect(new URL(filteredUrl).searchParams.get("createdTo")).toMatch(/Z$/);
  await page.reload();
  await expect(page.getByLabel("起始日期", { exact: true })).toHaveValue(
    dates.local,
  );
  await expect(page.getByLabel("结束日期", { exact: true })).toHaveValue(
    dates.local,
  );
  await page.getByLabel("起始日期", { exact: true }).fill("");
  await page.getByLabel("结束日期", { exact: true }).fill(dates.previous);
  await expect(
    page.getByText("没有符合条件的结果", { exact: true }),
  ).toBeVisible();
  await testInfo.attach("history-execution-evidence.json", {
    body: JSON.stringify(
      {
        timezoneId,
        runIds: runs.map((r) => r.id),
        freshRunId: fresh.id,
        secondPage,
        filteredUrl,
        dates,
      },
      null,
      2,
    ),
    contentType: "application/json",
  });
  await page.screenshot({
    path: testInfo.outputPath("history-local-date-filter.png"),
    fullPage: true,
  });
});
