import { expect, test } from "@playwright/test";
import { mkdirSync } from "node:fs";
import { resolve } from "node:path";
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
  await page.goto("/");
  await expect(page.getByTestId("nav-workflow-packages")).toHaveCount(0);
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
      await page.goto(path);
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
