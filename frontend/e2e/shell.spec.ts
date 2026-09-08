import { expect, test } from "@playwright/test";
const routes = [
  { path: "/", label: "Dashboard", nav: "dashboard" },
  {
    path: "/workflow-packages",
    label: "Workflow Packages",
    nav: "workflow-packages",
  },
  { path: "/resources", label: "Resources", nav: "resources" },
  { path: "/plugins", label: "Plugins", nav: "plugins" },
  {
    path: "/scheduled-tasks",
    label: "Scheduled Tasks",
    nav: "scheduled-tasks",
  },
  { path: "/runs", label: "Runs", nav: "runs" },
];
test("generic navigation owns one route shell without embedded finance pages", async ({
  page,
}) => {
  await page.goto("/");
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
    for (const path of [
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
        await page.screenshot({
          path: testInfo.outputPath(`editor-${width}.png`),
          fullPage: true,
          animations: "disabled",
        });
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
