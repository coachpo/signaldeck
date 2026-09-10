import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, test } from "@playwright/test";
import { apiBase } from "./platform-fixtures";
import { connectTaskServices } from "./task-fixtures";
import {
  captureResponsiveEvidence,
  type ResponsiveObservation,
} from "./responsive-evidence";

test("UX01/03/06: four ordinary tasks execute with real plugins and retain reusable results", async ({
  page,
  request,
}, testInfo) => {
  test.setTimeout(360_000);
  const observationId = testInfo.testId.slice(-6);
  await connectTaskServices(request, false);
  const cases = [
    { title: "保存原文", key: "research_notes", workflow: "capture" },
    { title: "整理笔记", key: "research_notes", workflow: "research" },
    {
      title: "市场研究",
      key: "tradingagents_advisory_research",
      workflow: "research",
    },
    {
      title: "综合资料研究",
      key: "digital_oracle_researcher",
      workflow: "research",
    },
  ];
  const originalText = [
    "# Original evidence",
    "",
    "Original business evidence retained unchanged.",
    "",
    "1. First confirmed item",
    "2. Second confirmed item",
    "",
    "- Supporting evidence",
    "",
    "| Source | Detail |",
    "| --- | --- |",
    `| Notes | ${"long-column-".repeat(30)} |`,
    "",
    "```text",
    "long-code-".repeat(40),
    "```",
    "",
    "[Source documentation](https://example.com/evidence)",
  ].join("\n");
  const evidence = [];
  const visualEvidence: ResponsiveObservation[] = [];
  const evidenceDirectory = resolve("../output/playwright/task-experience");
  mkdirSync(evidenceDirectory, { recursive: true });
  for (const scenario of cases) {
    await page.goto("/tasks");
    const card = page
      .locator("section")
      .filter({
        has: page.getByRole("heading", { name: scenario.title, exact: true }),
      })
      .last();
    await card.getByRole("link", { name: "选择任务" }).click();
    await expect(
      page.getByRole("heading", { name: scenario.title, exact: true }),
    ).toBeVisible();
    if (scenario.key === "research_notes") {
      await page
        .getByLabel("标题", { exact: true })
        .fill(`${scenario.title} ${observationId}`);
      await page
        .getByLabel("原文", { exact: true })
        .fill(originalText);
      if (scenario.workflow === "research") {
        await page.getByLabel("查找已有笔记", { exact: true }).fill("Original");
        await page.getByLabel("整理并总结原文", { exact: true }).check();
      }
    } else {
      await page
        .getByLabel("想了解什么", { exact: true })
        .fill("Which changes and missing evidence should be considered?");
      if (scenario.key === "tradingagents_advisory_research") {
        await page.getByRole("button", { name: "添加项目", exact: true }).click();
        await page.getByLabel("研究对象", { exact: true }).fill("MSFT");
        await expect(
          page.getByLabel("包含风险分析", { exact: true }),
        ).toBeChecked();
      }
    }
    visualEvidence.push(
      ...(await captureResponsiveEvidence(
        page,
        evidenceDirectory,
        `${scenario.workflow}-${scenario.key}-form`,
        page.getByRole("heading", { name: scenario.title, exact: true }),
        [
          {
            name: "设置重复执行",
            locator: page.getByRole("button", {
              name: "设置重复执行",
              exact: true,
            }),
          },
        ],
      )),
    );
    if (scenario.workflow === "capture") {
      const mode = page.getByRole("switch", { name: "专家模式", exact: true });
      await mode.click();
      await mode.click();
      await expect(page.getByLabel("原文", { exact: true })).toHaveValue(
        originalText,
      );
      await page
        .getByText("保存常用输入或收藏任务（可选）", { exact: true })
        .click();
      await page.getByLabel("配置名称").fill(`常用原文 ${observationId}`);
      await page.getByRole("button", { name: "保存为新配置" }).click();
      await expect(
        page.getByText(
          "已保存，可在任务首页找回。保存不会启动任务或创建计划。",
          { exact: true },
        ),
      ).toBeVisible();
    }
    await expect(page.getByRole("region", { name: "本次有效设置" })).toBeVisible();
    if (scenario.title === "整理笔记") {
      const connection = page
        .locator("details")
        .filter({
          has: page.locator("summary", { hasText: "research-model · 补齐连接" }),
        })
        .last();
      await connection.locator("summary").click();
      await expect(connection.getByText("没有适用于此任务的部署方服务预设", { exact: false })).toHaveCount(0);
      await expect(connection.getByText("请选择部署方提供的服务，再确认业务范围与保存位置。", { exact: true })).toBeVisible();
      await connection.getByLabel("部署方提供的服务").focus();
      await page.keyboard.press("Enter");
      await page.getByRole("option", { name: "本地受控研究服务" }).click();
      await connection.getByLabel("本地测试密钥").fill("fake-local-key");
      await connection
        .getByLabel("确认使用以上服务、账户、业务范围及保存位置")
        .check();
      await connection.getByRole("button", { name: "保存连接" }).click();
      await expect(page.getByLabel("原文", { exact: true })).toHaveValue(
        originalText,
      );
    }
    await expect(
      page.getByRole("button", { name: "开始任务", exact: true }),
    ).toBeEnabled();
    await expect(
      page.getByRole("button", { name: "核对连接与本次设置", exact: true }),
    ).toHaveCount(0);
    visualEvidence.push(
      ...(await captureResponsiveEvidence(
        page,
        evidenceDirectory,
        `${scenario.workflow}-${scenario.key}-ready`,
        page.getByRole("heading", { name: scenario.title, exact: true }),
        [
          {
            name: "开始任务",
            locator: page.getByRole("button", {
              name: "开始任务",
              exact: true,
            }),
          },
        ],
      )),
    );
    const submissions: string[] = [];
    if (scenario.workflow === "capture") {
      await page.route(
        "**/workflow-packages/research_notes/launches",
        async (route) => {
          submissions.push(route.request().postDataJSON().launchId);
          if (submissions.length === 1) {
            await route.fetch();
            await route.abort("connectionfailed");
          } else await route.continue();
        },
      );
    }
    await page.getByRole("button", { name: "开始任务", exact: true }).click();
    if (scenario.workflow === "capture") {
      await page.getByRole("button", { name: "使用同一请求重试" }).click();
      await expect.poll(() => submissions.length).toBe(2);
      expect(submissions[1]).toBe(submissions[0]);
      await page.unroute("**/workflow-packages/research_notes/launches");
    }
    await expect(page).toHaveURL(/\/runs\/[^/?]+$/);
    const runId = new URL(page.url()).pathname.split("/").at(-1)!;
    await expect
      .poll(
        async () =>
          (await (await request.get(`${apiBase}/runs/${runId}`)).json()).status,
        { timeout: 90_000 },
      )
      .toBe("succeeded");
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "来源与时间" }),
    ).toBeVisible();
    const result = await (
      await request.get(`${apiBase}/runs/${runId}/result`)
    ).json();
    const run = await (await request.get(`${apiBase}/runs/${runId}`)).json();
    expect(result.sections).toEqual(expect.arrayContaining([
      expect.objectContaining({ kind: "markdown", label: scenario.key === "research_notes" ? "笔记正文" : "研究报告", value: expect.any(String) }),
      expect.objectContaining({ kind: "receipt", value: expect.any(Object), operationId: expect.any(String) }),
    ]));
    if (scenario.key === "digital_oracle_researcher") {
      expect(
        run.evidence.some(
          (item: { kind: string; toolId: string; status: string }) =>
            item.kind === "tool" &&
            item.toolId ===
              "signaldeck/digital-oracle/market_sentiment_lookup" &&
            item.status === "succeeded",
        ),
      ).toBe(true);
    }
    if (scenario.workflow === "capture") {
      expect(
        run.evidence.some((item: { kind: string }) => item.kind === "model"),
      ).toBe(false);
      const history = await (
        await request.get(`${apiBase}/runs`, {
          params: {
            q: `${scenario.title} ${observationId}`,
            workflowKey: "capture",
          },
        })
      ).json();
      expect(history.total).toBe(1);
    }
    if (scenario.workflow === "capture") {
      const body = page.getByRole("region", { name: "笔记正文", exact: true });
      await expect(body.locator("ol")).toHaveCSS("list-style-type", "decimal");
      await expect(body.locator("ul")).toHaveCSS("list-style-type", "disc");
      await expect(body.getByRole("heading", { name: "Original evidence" })).toBeVisible();
      await body.getByRole("link", { name: "Source documentation" }).focus();
      await expect(body.getByRole("link", { name: "Source documentation" })).toBeFocused();
    }
    if (scenario.title === "整理笔记") {
      const resources = await (await request.get(`${apiBase}/resources`)).json();
      const model = resources.items.find((item: { resourceId: string }) => item.resourceId === "research-model");
      expect(model.modelObservation).toMatchObject({ status: "succeeded", runId });
      expect(model.modelObservation.observedAt).toBeTruthy();
      expect(model.modelObservation.evidenceId).toBeTruthy();
    }
    evidence.push({ scenario: scenario.title, run, result });
    writeFileSync(
      resolve(evidenceDirectory, "four-scenario-run-artifact-evidence.json"),
      JSON.stringify(evidence, null, 2),
    );
    await page.screenshot({
      path: resolve(
        evidenceDirectory,
        `${scenario.workflow}-${scenario.key}.png`,
      ),
      fullPage: true,
    });
    visualEvidence.push(
      ...(await captureResponsiveEvidence(
        page,
        evidenceDirectory,
        `${scenario.workflow}-${scenario.key}-result`,
        page.getByRole("region", { name: scenario.key === "research_notes" ? "笔记正文" : "研究报告", exact: true }),
        [
          {
            name: "再运行一次",
            locator: page.getByRole("button", {
              name: "再运行一次",
              exact: true,
            }),
          },
          {
            name: "修改输入后开始",
            locator: page.getByRole("link", {
              name: "修改输入后开始",
              exact: true,
            }),
          },
          {
            name: "设置重复执行",
            locator: page.getByRole("link", {
              name: "设置重复执行",
              exact: true,
            }),
          },
          {
            name: "技术详情与调用证据",
            locator: page.getByRole("link", {
              name: "技术详情与调用证据",
              exact: true,
            }),
          },
        ],
      )),
    );
    writeFileSync(
      resolve(evidenceDirectory, "responsive-control-evidence.json"),
      JSON.stringify(visualEvidence, null, 2),
    );
    if (scenario.key !== "research_notes") {
      const popupPromise = page.waitForEvent("popup");
      await page
        .getByRole("link", { name: "在 Finance 中查看报告", exact: true })
        .first()
        .click();
      const reportPage = await popupPromise;
      await expect(reportPage.getByLabel("报告正文")).toContainText(
        "fake provider content",
      );
      const downloadPromise = reportPage.waitForEvent("download");
      await reportPage.getByRole("button", { name: "下载 Markdown" }).click();
      const download = await downloadPromise;
      expect(await download.failure()).toBeNull();
      await download.saveAs(
        resolve(evidenceDirectory, `${scenario.key}-report.md`),
      );
      await reportPage.close();
    }
    if (scenario.workflow === "capture") {
      expect(result.sections.find((section: { kind: string }) => section.kind === "markdown").value).toContain(
        originalText,
      );
      const before = JSON.stringify(run.spec);
      await page.getByRole("link", { name: "修改输入后开始" }).click();
      await expect(page.getByLabel("原文", { exact: true })).toHaveValue(
        originalText,
      );
      await page
        .getByLabel("原文", { exact: true })
        .fill("Changed input creates another immutable result.");
      await expect(page.getByRole("region", { name: "本次有效设置" })).toBeVisible();
      await page.getByRole("button", { name: "开始任务", exact: true }).click();
      await expect(page).not.toHaveURL(new RegExp(runId));
      expect(
        JSON.stringify(
          (await (await request.get(`${apiBase}/runs/${runId}`)).json()).spec,
        ),
      ).toBe(before);
    }
  }
  await testInfo.attach("four-scenario-run-artifact-evidence.json", {
    body: JSON.stringify(evidence, null, 2),
    contentType: "application/json",
  });
});
