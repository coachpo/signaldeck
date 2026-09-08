import { expect, test } from "@playwright/test";
import { apiBase } from "./platform-fixtures";
test("resource credentials are write-only through save and reload", async ({
  page,
  request,
}) => {
  const id = `model-${crypto.randomUUID().slice(0, 8)}`;
  await page.goto("/resources");
  await page.getByLabel("Resource ID").fill(id);
  await page
    .getByLabel("Resource configuration JSON")
    .fill(
      JSON.stringify({
        name: "Model connection",
        baseUrl: "http://127.0.0.1:18081/v1",
        modelId: "fake-model",
        apiStyle: "chat_completions",
        timeoutSeconds: 30,
      }),
    );
  await page
    .getByLabel("New credentials JSON")
    .fill('{"apiKey":"private-e2e-value"}');
  await page.getByRole("button", { name: "Save resource" }).click();
  await expect(page.getByLabel("New credentials JSON")).toHaveValue("");
  const response = await request.get(`${apiBase}/resources`);
  const body = await response.json();
  expect(JSON.stringify(body)).not.toContain("private-e2e-value");
  expect(
    body.items.find((item: { resourceId: string }) => item.resourceId === id)
      .hasCredentials,
  ).toBe(true);
  await page.reload();
  await page.getByRole("button", { name: `Edit ${id}`, exact: true }).click();
  await expect(page.getByLabel("New credentials JSON")).toHaveValue("");
});
