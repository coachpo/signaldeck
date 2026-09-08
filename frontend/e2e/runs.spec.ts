import { expect, test } from "@playwright/test";
import { apiBase, seed } from "./platform-fixtures";
const provider = `http://127.0.0.1:${process.env.SIGNALDECK_FAKE_PROVIDER_PORT ?? "18081"}`;
test("running cancellation reports actual stopped state and does not fabricate outputs", async ({
  page,
  request,
}, testInfo) => {
  const { key, model } = await seed(request);
  const heldModel = `held-${key}`;
  await request.post(`${provider}/control/hold/${heldModel}`);
  const updated = await request.post(`${apiBase}/resources`, {
    data: {
      resourceId: model,
      kind: "model",
      config: {
        name: "Held local model",
        baseUrl: `${provider}/v1`,
        modelId: heldModel,
        apiStyle: "chat_completions",
        timeoutSeconds: 60,
      },
    },
  });
  expect(updated.ok(), await updated.text()).toBeTruthy();
  const response = await request.post(
    `${apiBase}/workflow-packages/${key}/launches`,
    {
      data: {
        workflowKey: "main",
        parameters: { summary: "Cancellation evidence" },
        launchId: crypto.randomUUID(),
      },
    },
  );
  expect(response.ok(), await response.text()).toBeTruthy();
  const run = await response.json();
  try {
    await expect
      .poll(
        async () =>
          (
            await (
              await request.get(`${provider}/control/state/${heldModel}`)
            ).json()
          ).entered,
        { timeout: 60000 },
      )
      .toBe(1);
    await page.setViewportSize({ width: 375, height: 900 });
    await page.goto(`/runs/${run.id}`);
    await expect
      .poll(() =>
        page.evaluate(
          () =>
            document.documentElement.scrollWidth -
            document.documentElement.clientWidth,
        ),
      )
      .toBeLessThanOrEqual(1);
    await page
      .getByRole("button", { name: "取消本次运行", exact: true })
      .click();
    await expect
      .poll(
        async () =>
          (await (await request.get(`${apiBase}/runs/${run.id}`)).json())
            .status,
        { timeout: 30000 },
      )
      .toBe("cancelled");
    await expect(
      page.getByText("本次运行已取消", { exact: true }),
    ).toBeVisible();
    const detail = await (
      await request.get(`${apiBase}/runs/${run.id}`)
    ).json();
    expect(detail.output).toBeNull();
    expect(detail.cancelRequestedAt).toBeTruthy();
    expect(
      detail.evidence.some(
        (item: { kind: string; status: string }) =>
          item.kind === "model" && item.status === "succeeded",
      ),
    ).toBe(false);
    await page
      .getByRole("link", { name: "技术详情与调用证据", exact: true })
      .click();
    await page.getByRole("tab", { name: "Call evidence", exact: true }).click();
    await expect(page.getByLabel("Call ownership tree")).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("cancelled-run.png"),
      fullPage: true,
      animations: "disabled",
    });
  } finally {
    await request.post(`${provider}/control/release/${heldModel}`);
  }
});
