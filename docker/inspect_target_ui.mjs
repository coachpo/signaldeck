/** Inspect the real isolated stack and the exact runs created by its API check. */
import assert from "node:assert/strict";
import { readFile, writeFile } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const workspace = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const requireFrontend = createRequire(join(workspace, "frontend/package.json"));
const { chromium, expect } = requireFrontend("@playwright/test");
const [source, destination] = process.argv.slice(2);
assert(source && destination, "Usage: inspect_target_ui.mjs compose.json evidence-directory");
const evidence = JSON.parse(await readFile(source, "utf8"));
const origins = new Set([evidence.baseUrl, evidence.financeUrl].map((url) => {
  const parsed = new URL(url);
  assert(["localhost", "127.0.0.1", "[::1]"].includes(parsed.hostname));
  assert.equal(parsed.protocol, "http:");
  return parsed.origin;
}));
assert.equal(evidence.runIds.length, 4, "Expected large, model, report and schedule runs");
const checks = [];
const screenshots = [];
const errors = [];
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.route("**/*", (route) => {
    if (origins.has(new URL(route.request().url()).origin)) return route.continue();
    errors.push("Browser attempted a request outside the isolated application origins");
    return route.abort();
  });
  const page = await context.newPage();
  page.on("pageerror", (error) => errors.push(error.message));
  async function api(base, path) {
    assert(origins.has(new URL(base).origin));
    const response = await context.request.get(base + path);
    assert.equal(response.status(), 200, `GET ${path}`);
    const body = await response.text();
    assert(!body.includes("compose-fake-credential"), "Secret leaked in API read");
    return JSON.parse(body);
  }
  async function screenshot(name) {
    await page.screenshot({ path: join(destination, name), fullPage: true, animations: "disabled" });
    screenshots.push(name);
  }
  for (const [index, id] of evidence.runIds.entries()) {
    const run = await api(evidence.baseUrl, "/api/runs/" + encodeURIComponent(id));
    assert.equal(run.status, "succeeded");
    await page.goto(evidence.baseUrl + "/runs/" + encodeURIComponent(id));
    await expect(page.getByLabel("Workflow nodes", { exact: true })).toBeVisible();
    for (const node of run.spec.plan.nodeOrder) {
      await expect(page.getByLabel("Workflow nodes", { exact: true }).getByRole("button", { name: node, exact: true })).toBeVisible();
    }
    await screenshot(`run-${index}-graph.png`);
    await page.getByRole("tab", { name: "Call evidence", exact: true }).click();
    const tree = page.getByLabel("Call ownership tree", { exact: true });
    await expect(tree).toBeVisible();
    await expect(tree.getByRole("link")).toHaveCount(run.evidence.length);
    const parents = await tree.locator("a").evaluateAll((links) => Object.fromEntries(links.map((link) => {
      const id = new URL(link.href).searchParams.get("target");
      const parentItem = link.closest("li").parentElement.closest("li");
      const parentLink = parentItem?.querySelector("a");
      return [id, parentLink ? new URL(parentLink.href).searchParams.get("target") : null];
    })));
    for (const item of run.evidence) {
      const parent = run.evidence.some((entry) => entry.id === item.parentId) ? item.parentId : null;
      assert.equal(parents[item.id], parent, `Invocation parent of ${item.id}`);
    }
    if (index === 1) {
      assert(run.evidence.some((item) => item.kind === "model"));
      await screenshot("ui.png");
    }
    await page.getByRole("tab", { name: "Immutable snapshot", exact: true }).click();
    const snapshot = page.getByLabel("Frozen run specification JSON", { exact: true });
    await expect(snapshot).toBeVisible();
    assert.deepEqual(JSON.parse(await snapshot.inputValue()), run.spec);
    checks.push(`rendered graph, invocation parents and immutable snapshot for ${id}`);
    if (index === 0) {
      await page.getByRole("tab", { name: "Dependency / artifact DAG", exact: true }).click();
      await expect(page.getByLabel("Artifact lineage edges", { exact: true }).locator("li").first()).toBeVisible();
      await page.getByRole("button", { name: "Inspect artifact", exact: true }).first().click();
      const artifact = page.getByLabel("Artifact content text", { exact: true });
      await expect(artifact).toBeVisible();
      assert((await artifact.inputValue()).includes("Local Compose execution evidence."));
      await screenshot("large-artifact.png");
      checks.push("large content-addressed artifact loaded through the browser");
    }
  }
  const resources = await api(evidence.baseUrl, "/api/resources");
  const model = resources.items.find((item) => item.resourceId.startsWith("compose-model-"));
  assert(model?.hasCredentials);
  assert.equal(typeof model.credentialRevision, "string");
  assert(model.credentialRevision.length > 0);
  await page.goto(evidence.baseUrl + "/resources");
  await expect(page.getByText("Credentials configured", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Edit " + model.resourceId, exact: true }).click();
  await expect(page.getByLabel("New credentials JSON", { exact: true })).toHaveValue("");
  assert(!(await page.content()).includes("compose-fake-credential"));
  await screenshot("credentials.png");
  checks.push("API and resource UI expose credential state while retaining write-only values");
  const report = await api(evidence.financeUrl, "/api/reports/" + encodeURIComponent(evidence.financeReportSlug));
  await page.goto(evidence.financeUrl);
  await page.getByRole("tab", { name: "Reports", exact: true }).click();
  await page.getByRole("button", { name: new RegExp(report.name) }).click();
  await expect(page.getByLabel("Markdown content", { exact: true })).toHaveValue(report.content);
  assert(await page.getByLabel("Markdown content", { exact: true }).evaluate((element) => element.readOnly));
  await expect(page.getByRole("button", { name: "Save", exact: true })).toBeDisabled();
  await expect(page.getByText("Agent reports preserve the original run output.", { exact: true })).toBeVisible();
  await screenshot("finance-report.png");
  checks.push("Finance report renders original content and enforces read-only Agent output");
  assert.deepEqual(errors, [], "Browser errors or external requests");
  await writeFile(join(destination, "ui.json"), JSON.stringify({ status: "passed", checks, screenshots }, null, 2) + "\n");
  console.log(JSON.stringify({ status: "passed", checks, screenshots }));
} finally {
  await browser.close();
}
