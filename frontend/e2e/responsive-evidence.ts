import { expect, type Locator, type Page } from "@playwright/test";
import { resolve } from "node:path";

export interface ResponsiveObservation {
  screen: string;
  width: number;
  controls: Array<{ name: string; x: number; y: number; width: number; height: number }>;
}

/** Screenshots alone do not prove that controls can be reached or clicked. */
export async function captureResponsiveEvidence(
  page: Page,
  directory: string,
  screen: string,
  content: Locator,
  controls: Array<{ name: string; locator: Locator }>,
): Promise<ResponsiveObservation[]> {
  const observations: ResponsiveObservation[] = [];
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await expect(content).toBeVisible();
    await content.scrollIntoViewIfNeeded();
    await page.screenshot({
      path: resolve(directory, `${screen}-${width}-content.png`),
      animations: "disabled",
    });
    const checks: ResponsiveObservation["controls"] = [];
    for (const { name, locator } of controls) {
      await expect(locator).toBeEnabled();
      await locator.click({ trial: true });
      const bounds = await locator.boundingBox();
      expect(bounds, `${screen}/${width}: ${name} has a rendered box`).not.toBeNull();
      expect(bounds!.width, `${screen}/${width}: ${name} has usable width`).toBeGreaterThan(0);
      expect(bounds!.height).toBeGreaterThan(0);
      expect(bounds!.x, `${screen}/${width}: ${name} left edge`).toBeGreaterThanOrEqual(-1);
      expect(bounds!.x + bounds!.width, `${screen}/${width}: ${name} right edge`).toBeLessThanOrEqual(width + 1);
      expect(bounds!.y, `${screen}/${width}: ${name} top edge`).toBeGreaterThanOrEqual(-1);
      expect(bounds!.y + bounds!.height, `${screen}/${width}: ${name} bottom edge`).toBeLessThanOrEqual(901);
      checks.push({ name, ...bounds! });
    }
    await page.screenshot({
      path: resolve(directory, `${screen}-${width}-actions.png`),
      animations: "disabled",
    });
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(1);
    observations.push({ screen, width, controls: checks });
  }
  return observations;
}
