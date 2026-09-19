import { expect, type Locator, type Page } from "@playwright/test";
import { resolve } from "node:path";

export interface ResponsiveObservation {
  screen: string;
  width: number;
  controls: Array<{ name: string; x: number; y: number; width: number; height: number }>;
}

/** Measures an element against what the viewport and every clipping ancestor actually show. */
function measureReach(element: Element) {
  const visibleArea = (from: Element | null) => {
    const area = { top: 0, right: innerWidth, bottom: innerHeight, left: 0 };
    for (let node = from; node; node = node.parentElement) {
      const style = getComputedStyle(node);
      const box = node.getBoundingClientRect();
      const top = box.top + node.clientTop;
      const left = box.left + node.clientLeft;
      if (style.overflowY !== "visible") {
        area.top = Math.max(area.top, top);
        area.bottom = Math.min(area.bottom, top + node.clientHeight);
      }
      if (style.overflowX !== "visible") {
        area.left = Math.max(area.left, left);
        area.right = Math.min(area.right, left + node.clientWidth);
      }
    }
    return area;
  };
  let scroller = element.parentElement;
  while (scroller && !(/auto|scroll/.test(getComputedStyle(scroller).overflowY) && scroller.scrollHeight > scroller.clientHeight)) {
    scroller = scroller.parentElement;
  }
  const region = visibleArea(scroller);
  const area = visibleArea(element.parentElement);
  const rect = element.getBoundingClientRect();
  const target = document.elementFromPoint((rect.left + rect.right) / 2, (rect.top + rect.bottom) / 2);
  return {
    // Top, right, bottom and left distance by which the element extends past the shown area.
    overflow: [area.top - rect.top, rect.right - area.right, rect.bottom - area.bottom, area.left - rect.left],
    intersects: rect.bottom > area.top && rect.top < area.bottom && rect.right > area.left && rect.left < area.right,
    hit: target !== null && element.contains(target),
    pointer: { x: (region.left + region.right) / 2, y: (region.top + region.bottom) / 2 },
  };
}

/**
 * Only wheel input proves reachability: locator actions and scrollIntoViewIfNeeded also
 * scroll `overflow: hidden` containers that no user can scroll.
 */
async function wheelIntoView(page: Page, target: Locator, label: string, whole: boolean) {
  await expect(async () => {
    const { overflow, intersects, hit, pointer } = await target.evaluate(measureReach);
    const [top, , bottom] = overflow;
    const reached = whole ? Math.max(...overflow) <= 1 && hit : intersects;
    if (!reached && (top > 1) !== (bottom > 1)) {
      await page.mouse.move(pointer.x, pointer.y);
      await page.mouse.wheel(0, bottom > 1 ? Math.min(bottom + 24, 400) : -Math.min(top + 24, 400));
    }
    expect(reached, `${label} is reachable by wheel (overflow ${overflow.map(Math.round).join("/")}, pointer target ${hit})`).toBe(true);
  }).toPass({ timeout: 15_000, intervals: [100] });
  await expect(target, label).toBeInViewport();
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
    await wheelIntoView(page, content, `${screen}/${width}: content`, false);
    await page.screenshot({
      path: resolve(directory, `${screen}-${width}-content.png`),
      animations: "disabled",
    });
    const checks: ResponsiveObservation["controls"] = [];
    for (const { name, locator } of controls) {
      await expect(locator).toBeEnabled();
      await wheelIntoView(page, locator, `${screen}/${width}: ${name}`, true);
      const bounds = await locator.boundingBox();
      expect(bounds, `${screen}/${width}: ${name} has a rendered box`).not.toBeNull();
      expect(bounds!.width, `${screen}/${width}: ${name} has usable width`).toBeGreaterThan(0);
      expect(bounds!.height).toBeGreaterThan(0);
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
