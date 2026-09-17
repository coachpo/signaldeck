import { expect, test, type Page } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
import { apiBase, seed } from "./platform-fixtures";
async function openSavedTaskCatalog(page: Page) {
  const loading = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/workflow-packages" && response.request().method() === "GET");
  await page.goto("/");
  const response = await loading;
  expect(response.ok(), await response.text()).toBe(true);
  const packages = await response.json();
  const hrefs: string[] = packages.items.flatMap((pkg: { key: string; definition: { workflows: Record<string, unknown> } }) =>
    Object.keys(pkg.definition.workflows).map((workflowKey) => `/tasks/new?packageKey=${encodeURIComponent(pkg.key)}&workflowKey=${encodeURIComponent(workflowKey)}`));
  await expect(page.getByRole("link", { name: "选择任务", exact: true })).toHaveCount(hrefs.length);
  for (const href of hrefs) await expect(page.locator(`a[href="${href}"]`)).toBeVisible();
  return hrefs;
}
const routes = [
  { path: "/", label: "任务", nav: "tasks" },
  {
    path: "/workflow-packages",
    label: "制作工作流",
    nav: "workflow-packages",
  },
  { path: "/resources", label: "服务连接", nav: "resources" },
  { path: "/plugins", label: "扩展服务", nav: "plugins" },
  { path: "/settings", label: "设置", nav: "settings" },
  { path: "/runs", label: "结果", nav: "runs" },
  { path: "/attention", label: "执行更新", nav: "attention" },
];
test("generic navigation owns one route shell without statically compiled business pages", async ({
  page,
}) => {
  const taskHrefs = await openSavedTaskCatalog(page);
  await expect(page.getByTestId("nav-workflow-packages")).toHaveCount(0);
  await expect(page.getByTestId("nav-attention")).toBeVisible();
  const expertEntry = page.getByRole("link", {
    name: "全部任务定义与专家制作",
    exact: true,
  });
  await expect(expertEntry).toHaveCount(0);
  await page.getByRole("switch", { name: "专家模式", exact: true }).check();
  await expect(expertEntry).toBeVisible();
  await expertEntry.click();
  await expect(page).toHaveURL("/workflow-packages");
  await page.getByTestId("nav-tasks").click();
  await page.getByRole("switch", { name: "专家模式", exact: true }).uncheck();
  await expect(expertEntry).toHaveCount(0);
  for (const href of taskHrefs) await expect(page.locator(`a[href="${href}"]`)).toBeVisible();
  await page.getByRole("switch", { name: "专家模式", exact: true }).check();
  for (const route of routes) {
    await page.getByTestId(`nav-${route.nav}`).click();
    await expect(page).toHaveURL(route.path);
    await expect(
      page.getByRole("heading", { name: route.label, level: 1, exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("main")).toHaveCount(1);
  }
  await expect(page.getByTestId("nav-reports")).toHaveCount(0);
  await expect(page.getByTestId("nav-templates")).toHaveCount(0);
  await page.goto("/templates");
  await expect(
    page.getByRole("heading", { name: "找不到页面" }),
  ).toBeVisible();
});
test("opens creation, edit and detail pages when plain HTTP withholds secure-context APIs", async ({
  page,
  request,
}) => {
  const { key } = await seed(request);
  const launched = await request.post(`${apiBase}/workflow-packages/${key}/launches`, {
    data: { workflowKey: "main", parameters: { summary: "Plain HTTP result" }, launchId: crypto.randomUUID() },
  });
  expect(launched.ok(), await launched.text()).toBeTruthy();
  const run = await launched.json();
  const scheduleName = `Plain HTTP ${key}`;
  const created = await request.post(`${apiBase}/schedules`, {
    data: {
      name: scheduleName,
      packageKey: key,
      workflowKey: "main",
      parameters: { summary: "Plain HTTP schedule" },
      cron: "0 9 * * *",
      timeZone: "UTC",
      overlapPolicy: "skip",
      catchupWindowSeconds: 60,
      paused: true,
    },
  });
  expect(created.ok(), await created.text()).toBeTruthy();
  const schedule = await created.json();
  await expect
    .poll(async () => (await (await request.get(`${apiBase}/runs/${run.id}`)).json()).status, { timeout: 60000 })
    .toBe("succeeded");
  // Browsers expose these only in secure contexts, which a LAN address over HTTP is not.
  await page.addInitScript(() => {
    Reflect.deleteProperty(Crypto.prototype, "randomUUID");
    Reflect.deleteProperty(Crypto.prototype, "subtle");
    Reflect.deleteProperty(Navigator.prototype, "clipboard");
  });
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  const pages: [string, (page: Page) => Promise<void>][] = [
    [`/tasks/new?packageKey=${key}&workflowKey=main`, (p) => expect(p.getByRole("button", { name: "开始任务" })).toBeVisible()],
    ["/workflow-packages/new", (p) => expect(p.getByLabel("工作流集名称")).toBeVisible()],
    ["/resources", (p) => expect(p.getByRole("heading", { name: "服务连接", level: 1 })).toBeVisible()],
    ["/scheduled-tasks", (p) => expect(p.getByRole("heading", { name: scheduleName })).toBeVisible()],
    ["/scheduled-tasks/new", (p) => expect(p.getByRole("button", { name: "启用自动执行" })).toBeVisible()],
    [`/scheduled-tasks/${schedule.id}`, (p) => expect(p.getByRole("button", { name: "保存安排" })).toBeVisible()],
    [`/runs/${run.id}`, (p) => expect(p.getByRole("button", { name: "再运行一次" })).toBeVisible()],
    [`/workflow-packages/${key}`, async (p) => {
      await p.getByRole("button", { name: "添加任务流程" }).click();
      await expect(p.getByRole("button", { name: "任务流程 2", exact: true })).toBeVisible();
    }],
  ];
  for (const [path, ready] of pages) {
    await page.goto(path);
    await ready(page);
    await expect(page.getByTestId("route-error-page")).toHaveCount(0);
  }
  expect(pageErrors).toEqual([]);
});
test("reopens a page whose file failed to load once and stops after one reload when it keeps failing", async ({ page }) => {
  let loads = 0;
  page.on("load", () => loads++);
  let failures = 1;
  // Stands in for a file replaced by a restart or redeploy while the tab stayed open.
  await page.route(/\/assets\/attention-[^/]+\.js$/, (route) => (failures-- > 0 ? route.abort() : route.continue()));
  await page.goto("/");
  await expect(page.getByTestId("route-tasks")).toBeVisible();
  await Promise.all([page.waitForEvent("load"), page.getByTestId("nav-attention").click()]);
  await expect(page.getByRole("heading", { name: "执行更新", level: 1 })).toBeVisible();
  await expect(page).toHaveURL("/attention");
  expect(loads).toBe(2);

  failures = Number.POSITIVE_INFINITY;
  await page.goto("/");
  await expect(page.getByTestId("route-tasks")).toBeVisible();
  await Promise.all([page.waitForEvent("load"), page.getByTestId("nav-attention").click()]);
  await expect(page.getByTestId("route-error-page")).toBeVisible();
  await expect(page).toHaveURL("/attention");
  expect(loads).toBe(4);
  const reloadedAgain = await page.waitForEvent("load", { timeout: 3_000 }).then(() => true, () => false);
  expect(reloadedAgain).toBe(false);
  await expect(page.getByTestId("route-error-page")).toBeVisible();
});
test("opens the task home for a location path with repeated leading slashes", async ({ page, baseURL }) => {
  await page.goto(`${baseURL}//`);
  await expect(page.getByTestId("route-tasks")).toBeVisible();
  await expect(page.getByTestId("route-error-page")).toHaveCount(0);
});
for (const width of [375, 768, 1024, 1440])
  test(`definition workspace and resources fit width ${width}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const directory = resolve("../output/playwright/shell-experience");
    mkdirSync(directory, { recursive: true });
    for (const path of [
      "/",
      "/settings",
      "/workflow-packages/new",
      "/resources",
      "/scheduled-tasks/new",
      "/plugins",
      "/runs",
      "/attention",
      "/runs/compare",
    ]) {
      if (path === "/") await openSavedTaskCatalog(page);
      else await page.goto(path);
      await expect(page.getByRole("main")).toBeVisible();
      if (path === "/workflow-packages/new") {
        await expect(page.getByLabel("工作流集名称")).toBeVisible();
      }
      const screenshot = resolve(
        directory,
        `${path.replaceAll("/", "-") || "tasks"}-${width}.png`,
      );
      await page.screenshot({
        path: screenshot,
        fullPage: true,
        animations: "disabled",
      });
      await testInfo.attach(`${path}-${width}`, {
        path: screenshot,
        contentType: "image/png",
      });
      if (path === "/") {
        const expertEntry = page.getByRole("link", {
          name: "全部任务定义与专家制作",
          exact: true,
        });
        await expect(expertEntry).toHaveCount(0);
        await page.getByRole("switch", { name: "专家模式", exact: true }).check();
        await expertEntry.click({ trial: true });
        const bounds = await expertEntry.boundingBox();
        expect(bounds).not.toBeNull();
        expect(bounds!.x).toBeGreaterThanOrEqual(-1);
        expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1);
        expect(bounds!.y).toBeGreaterThanOrEqual(-1);
        expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(901);
        const expertScreenshot = resolve(directory, `home-expert-${width}.png`);
        await page.screenshot({
          path: expertScreenshot,
          fullPage: true,
          animations: "disabled",
        });
        await testInfo.attach(`home-expert-${width}`, {
          path: expertScreenshot,
          contentType: "image/png",
        });
        await page.getByRole("switch", { name: "专家模式", exact: true }).uncheck();
      }
      await expect
        .poll(() =>
          page.evaluate(
            () =>
              document.documentElement.scrollWidth -
              document.documentElement.clientWidth,
          ),
        )
        .toBeLessThanOrEqual(1);
    }
  });
