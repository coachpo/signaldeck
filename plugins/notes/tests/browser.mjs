import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { mkdir } from 'node:fs/promises';
import assert from 'node:assert/strict';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const { chromium, expect } = require('@playwright/test');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', error => errors.push(error.message));
const screenshots = path.join(root, 'output/playwright/notes-ux');
await mkdir(screenshots, { recursive: true });
try {
  // Goal: locate a saved summary, inspect its source, and return to the same search.
  let releaseInitialRead, sawInitialRead, finishedInitialRead;
  const initialRead = new Promise(resolve => { sawInitialRead = resolve; });
  const initialGate = new Promise(resolve => { releaseInitialRead = resolve; });
  const initialReadFinished = new Promise(resolve => { finishedInitialRead = resolve; });
  const holdCollections = async route => {
    const response = await route.fetch();
    sawInitialRead();
    await initialGate;
    await route.fulfill({ response });
    finishedInitialRead();
  };
  await page.route('**/api/collections', holdCollections);
  try {
    await page.goto(process.env.NOTES_TEST_URL);
    await initialRead;
    await expect(page.getByRole('status')).toHaveText('正在读取笔记…');
    await expect(page.getByLabel('检索范围')).toBeDisabled();
    await expect(page.getByLabel('查找标题或正文')).toBeDisabled();
    await expect(page.getByRole('button', { name: '搜索', exact: true })).toBeDisabled();
    await page.screenshot({ path: path.join(screenshots, 'initial-loading.png'), fullPage: true });
  } finally {
    releaseInitialRead();
    await initialReadFinished;
    await page.unroute('**/api/collections', holdCollections);
  }
  await expect(page.locator('#summary')).toHaveText('本页 1 条笔记');
  await expect(page.getByLabel('检索范围')).toBeEnabled();
  await page.getByLabel('检索范围').selectOption({ label: '包含整理结果' });
  await page.getByRole('button', { name: '搜索', exact: true }).click();
  await expect(page.locator('#summary')).toHaveText('本页 2 条笔记');
  await page.getByRole('link', { name: /访谈要点整理/ }).click();
  await page.getByRole('link', { name: '访谈原始记录', exact: true }).waitFor();
  assert.doesNotMatch(await page.locator('body').innerText(), /browser-.*-internal-identity|保存标识/);
  await page.screenshot({ path: path.join(screenshots, 'source-title.png'), fullPage: true });
  await page.getByRole('link', { name: '访谈原始记录', exact: true }).click();
  await expect(page.locator('#noteText')).toHaveText('用户原文 inputs.my_code 保持原样。');
  await page.goBack();
  await page.getByRole('link', { name: '访谈原始记录', exact: true }).waitFor();
  await page.reload();
  await page.getByRole('link', { name: '访谈原始记录', exact: true }).waitFor();
  // Controlled read failure proves that the summary stays readable and uncertainty is explicit.
  const failSource = route => route.fulfill({ status: 503, contentType: 'application/json', body: '{"message":"internal stack /storage/notes"}' });
  await page.route('**/api/note?id=browser-original-internal-identity', failSource);
  await page.reload();
  await page.getByText('这份来源暂时无法读取，尚不能核对其内容。', { exact: false }).waitFor();
  await expect(page.locator('#noteText')).toHaveText('整理结果，待结合原文核对。');
  assert.doesNotMatch(await page.locator('body').innerText(), /internal-identity|internal stack|\/storage/);
  await page.screenshot({ path: path.join(screenshots, 'source-unavailable.png'), fullPage: true });
  await page.unroute('**/api/note?id=browser-original-internal-identity', failSource);
  await page.getByRole('link', { name: '重新查看来源', exact: true }).click();
  await page.getByRole('heading', { name: '访谈原始记录', exact: true }).waitFor();
  await page.getByRole('link', { name: '← 返回笔记', exact: true }).click();
  await expect(page.getByLabel('检索范围')).toHaveValue('true');
  await expect(page.locator('#summary')).toHaveText('本页 2 条笔记');
  const failCollections = route => route.fulfill({ status: 503, contentType: 'application/json', body: '{}' });
  await page.route('**/api/collections', failCollections);
  await page.reload();
  await expect(page.getByRole('status')).toContainText('笔记暂时无法读取，请稍后重试。');
  await expect(page.getByRole('button', { name: '搜索', exact: true })).toBeEnabled();
  await page.unroute('**/api/collections', failCollections);
  await page.getByRole('button', { name: '重新读取', exact: true }).click();
  await expect(page.locator('#summary')).toHaveText('本页 2 条笔记');
  await expect(page.getByLabel('检索范围')).toHaveValue('true');
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: 'passed', screenshots, checks: ['initial loading controls', 'source title', 'body preservation', 'back and refresh', 'source failure and recovery'] }));
} finally { await browser.close(); }
