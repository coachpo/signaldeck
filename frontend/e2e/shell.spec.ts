import { expect, test, type Page } from "@playwright/test";
import { apiBase } from "./platform-fixtures";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
async function openSavedTaskCatalog(page: Page) {
  const loading = page.waitForResponse((response) => response.url() === `${apiBase}/workflow-packages` && response.request().method() === "GET");
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
    label: "Workflow Packages",
    nav: "workflow-packages",
  },
  { path: "/resources", label: "Resources", nav: "resources" },
  { path: "/plugins", label: "Plugins", nav: "plugins" },
  { path: "/settings", label: "设置", nav: "settings" },
  { path: "/runs", label: "结果", nav: "runs" },
];
test("generic navigation owns one route shell without embedded finance pages", async ({
  page,
}) => {
  const taskHrefs = await openSavedTaskCatalog(page);
  await expect(page.getByTestId("nav-workflow-packages")).toHaveCount(0);
  const expertEntry = page.getByRole("link", {
    name: "全部任务定义与专家制作",
    exact: true,
  });
  await expect(expertEntry).toHaveCount(0);
  for (const href of taskHrefs) await expect(page.locator(`a[href="${href}"]`)).toBeVisible();
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
      page.getByRole("heading", { name: route.label, exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("main")).toHaveCount(1);
  }
  await expect(page.getByTestId("nav-reports")).toHaveCount(0);
  await expect(page.getByTestId("nav-templates")).toHaveCount(0);
  await page.goto("/templates");
  await expect(
    page.getByRole("heading", { name: "Page not found" }),
  ).toBeVisible();
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
    ]) {
      if (path === "/") await openSavedTaskCatalog(page);
      else await page.goto(path);
      await expect(page.getByRole("main")).toBeVisible();
      if (path === "/workflow-packages/new") {
        await expect(page.getByLabel("Workflow Package YAML")).toBeVisible();
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
