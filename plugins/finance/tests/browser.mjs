import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import { mkdir, readFile } from 'node:fs/promises';
import assert from 'node:assert/strict';
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../..');
const require = createRequire(path.join(root, 'frontend/package.json'));
const { chromium } = require('@playwright/test');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage();
const errors = [];
page.on('pageerror', e => errors.push(e.message));
const base = process.env.FINANCE_TEST_URL;
const artifactDir = path.join(root, 'output/playwright/finance-ux');
async function holdMutation(method, pattern) {
  let release;
  let observed;
  const gate = new Promise(resolve => { release = resolve; });
  const started = new Promise(resolve => { observed = resolve; });
  const handler = async route => {
    if (route.request().method() !== method) return route.continue();
    const response = await route.fetch();
    observed();
    await gate;
    await route.fulfill({ response });
  };
  await page.route(pattern, handler);
  return { started, release, dispose: () => page.unroute(pattern, handler) };
}
async function assertMutationLocked() {
  for (const selector of ['#mode', '[data-tab="reports"]', '[data-tab="templates"]', '#new', '#name', '#content', '#delete', '#upload', '#file'])
    assert.equal(await page.locator(selector).isDisabled(), true, selector + ' must retain the active operation and draft');
  assert.match(await page.locator('#message').innerText(), /正在处理/);
}

await mkdir(artifactDir, { recursive: true });
try {
  await page.goto(base);
  await page.getByRole('button', { name: '使用已有格式', exact: true }).click();
  await page.getByRole('button', { name: /研究格式/ }).click();
  await page.getByRole('button', { name: '预览报告', exact: true }).click();
  assert.equal(await page.getByLabel('公司名称（必填）').evaluate(el => el.validity.valueMissing), true);
  assert.equal(await page.locator('#preview').isVisible(), false);
  await page.getByLabel('公司名称（必填）').fill('Example Company');
  await page.getByRole('button', { name: '预览报告', exact: true }).click();
  await page.getByRole('button', { name: '生成报告', exact: true }).waitFor({ state: 'visible' });
  await page.waitForFunction(() => !document.getElementById('generate').disabled);
  assert.match(await page.locator('#preview').innerText(), /Example Company/);
  assert.doesNotMatch(await page.locator('#preview').innerText(), /Missing input/);
  await page.getByRole('button', { name: '开启专家模式' }).click();
  await page.getByLabel('Markdown 内容', { exact: true }).fill('<!-- input: company | 公司名称 | required -->\n<!-- input: notes | 补充说明 | optional -->\n# {{inputs.company}}\n草稿 {{inputs.notes}}');
  await page.getByRole('button', { name: '切换普通模式' }).click();
  assert.equal(await page.getByLabel('公司名称（必填）').inputValue(), 'Example Company');
  await page.getByRole('button', { name: '开启专家模式' }).click();
  assert.match(await page.getByLabel('Markdown 内容', { exact: true }).inputValue(), /草稿/);
  const draftContent = await page.getByLabel('Markdown 内容', { exact: true }).inputValue();
  await page.getByLabel('Markdown 内容', { exact: true }).fill(draftContent + '\n{{unknown.field}}');
  await page.getByRole('button', { name: '编译并预览草稿', exact: true }).click();
  await page.getByText('编译问题：', { exact: false }).waitFor();
  assert.equal(await page.getByRole('button', { name: '生成报告', exact: true }).isDisabled(), true);
  await page.getByLabel('Markdown 内容', { exact: true }).fill(draftContent);

  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(artifactDir, `author-${width}.png`), fullPage: true });
  }
  const pendingSave = await holdMutation('PATCH', '**/api/templates/*');
  let expectedDraft = await page.locator('#content').inputValue();
  try {
    await page.getByRole('button', { name: '保存', exact: true }).click();
    await pendingSave.started;
    // A slow successful response must never overwrite edits made after submission.
    if (!await page.locator('#content').isDisabled()) {
      expectedDraft += '\nChanged while saving';
      await page.locator('#content').fill(expectedDraft);
    }
    pendingSave.release();
    await page.getByText('已保存。', { exact: true }).waitFor();
    assert.equal(await page.locator('#content').inputValue(), expectedDraft, 'a save response must not discard newer draft content');
  } finally { pendingSave.release(); await pendingSave.dispose(); }
  // Exercise the same operation boundary with a mode/tab switch available nearby.
  const secondSave = await holdMutation('PATCH', '**/api/templates/*');
  try {
    await page.getByRole('button', { name: '保存', exact: true }).click();
    await secondSave.started;
    await assertMutationLocked();
    secondSave.release();
    await page.getByText('已保存。', { exact: true }).waitFor();
  } finally { secondSave.release(); await secondSave.dispose(); }
  assert.equal(await page.locator('#mode').isDisabled(), false);
  const failSave = async route => route.request().method() === 'PATCH'
    ? route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ message: 'Controlled temporary failure' }) })
    : route.continue();
  await page.route('**/api/templates/*', failSave);
  try {
    await page.getByRole('button', { name: '保存', exact: true }).click();
    await page.getByText('Controlled temporary failure', { exact: true }).waitFor();
    assert.equal(await page.locator('#mode').isDisabled(), false);
    assert.equal(await page.locator('#content').inputValue(), expectedDraft);
  } finally { await page.unroute('**/api/templates/*', failSave); }
  await page.getByRole('button', { name: '切换普通模式' }).click();
  await page.getByRole('button', { name: '预览报告', exact: true }).click();
  await page.waitForFunction(() => !document.getElementById('generate').disabled);
  const expected = await page.locator('#preview').innerText();
  const pendingGeneration = await holdMutation('POST', '**/api/reports/compile/*');
  try {
    await page.getByRole('button', { name: '生成报告', exact: true }).click();
    await pendingGeneration.started;
    await assertMutationLocked();
    pendingGeneration.release();
    await page.getByText('报告已生成并保存。', { exact: true }).waitFor();
  } finally { pendingGeneration.release(); await pendingGeneration.dispose(); }

  assert.equal(await page.locator('#report-body').innerText(), expected);
  const deepLink = page.url();
  assert.match(deepLink, /\?report=/);
  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '下载 Markdown', exact: true }).click();
  const download = await downloadPromise;
  assert.match(await readFile(await download.path(), 'utf8'), /Example Company/);
  const reportId = await page.evaluate(() => selected.id);
  await page.goto(base + '?reportId=' + reportId);
  await page.locator('#reading').waitFor({state:'visible'});
  assert.equal(await page.locator('#report-body').innerText(), expected);
  await page.reload();
  await page.locator("#reading").waitFor({state:"visible"});
  assert.equal(await page.locator('#report-body').innerText(), expected);
  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.screenshot({ path: path.join(artifactDir, `report-${width}.png`), fullPage: true });
  }
  await page.getByLabel('搜索全部报告或格式').fill('Report');
  await page.getByRole('button', { name: '查询', exact: true }).click();
  await page.waitForFunction(() => document.querySelectorAll('#list .entry').length === 15);
  await page.getByRole('button', { name: '下一页', exact: true }).click();
  await page.getByText('第 2 页', { exact: true }).waitFor();
  assert.equal(await page.locator('#list .entry').count(), 4);
  await page.getByRole('button', { name: '开启专家模式' }).click();
  const pendingUpload = await holdMutation('POST', '**/api/reports/upload');
  try {
    await page.locator('#file').setInputFiles({ name: 'pending-upload.md', mimeType: 'text/markdown', buffer: Buffer.from('# Uploaded after waiting') });
    await pendingUpload.started;
    await assertMutationLocked();
    pendingUpload.release();
    await page.getByText('报告已上传。', { exact: true }).waitFor();
    assert.match(await page.locator('#report-body').innerText(), /Uploaded after waiting/);
  } finally { pendingUpload.release(); await pendingUpload.dispose(); }
  const pendingDelete = await holdMutation('DELETE', '**/api/reports/*');
  try {
    page.once('dialog', dialog => dialog.accept());
    await page.getByRole('button', { name: '删除报告', exact: true }).click();
    await pendingDelete.started;
    await assertMutationLocked();
    pendingDelete.release();
    await page.getByText('已删除。', { exact: true }).waitFor();
  } finally { pendingDelete.release(); await pendingDelete.dispose(); }
  assert.equal(await page.locator('#mode').isDisabled(), false);
  await page.goto(base + '?report=not_found');
  await page.locator('#message.error').waitFor();
  assert.equal(await page.locator('#reading').isVisible(), false);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: 'passed', deepLink, screenshots: artifactDir, checks: ['ordinary form', 'optional field', 'preview/generation', 'draft roundtrip', 'deep link reload', 'download', 'history page 2', '404', 'four viewport widths', 'delayed save/generate/upload/delete', 'save failure unlock'] }));
} finally { await browser.close(); }
