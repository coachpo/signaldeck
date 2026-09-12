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
async function assertRefreshKeepsWork(selector, value) {
  const pendingDialog = page.waitForEvent('dialog', { timeout: 5000 });
  const reload = page.reload({ timeout: 1000 }).catch(error => error);
  const dialog = await pendingDialog;
  assert.equal(dialog.type(), 'beforeunload');
  await dialog.dismiss();
  await reload;
  assert.equal(await page.locator(selector).inputValue(), value);
}

await mkdir(artifactDir, { recursive: true });
try {
  await page.goto(base);
  await page.getByRole('button', {name:'切换外观'}).click();
  await page.getByRole('menuitem', {name:'深色',exact:true}).click();
  await page.reload();
  assert.equal(await page.locator('html').evaluate(el=>el.classList.contains('dark')),true);
  await page.screenshot({path:path.join(artifactDir,'dark-workspace.png'),fullPage:true});
  await page.getByRole('button', {name:'切换外观'}).click();
  await page.getByRole('menuitem', {name:'浅色',exact:true}).click();
  await page.waitForFunction(()=>!document.documentElement.classList.contains('dark'));
  await page.getByRole('button', { name: /任务生成结果/ }).click();
  assert.equal(await page.getByRole('heading', { name: '任务生成结果', exact: true }).count(), 1);
  assert.doesNotMatch(await page.locator('body').innerText(), /browser-private|createdBy|来源与技术证据/);
  await page.screenshot({ path: path.join(artifactDir, 'report-source.png'), fullPage: true });
  await page.getByRole('button', { name: '使用已有格式', exact: true }).click();
  await page.getByRole('button', { name: /研究格式/ }).click();
  await page.getByRole('button', { name: '预览报告', exact: true }).click();
  assert.equal(await page.getByLabel('公司名称（必填）').evaluate(el => el.validity.valueMissing), true);
  assert.equal(await page.locator('#preview').isVisible(), false);
  await page.getByLabel('公司名称（必填）').fill('Example Company');
  await assertRefreshKeepsWork('#input-company', 'Example Company');
  await page.getByRole('button', { name: '预览报告', exact: true }).click();
  await page.getByRole('button', { name: '生成报告', exact: true }).waitFor({ state: 'visible' });
  await page.waitForFunction(() => !document.getElementById('generate').disabled);
  assert.match(await page.locator('#preview').innerText(), /Example Company/);
  assert.doesNotMatch(await page.locator('#preview').innerText(), /Missing input/);
  await page.getByRole('switch', { name: '专家模式' }).click();
  assert.doesNotMatch(await page.getByRole('textbox', { name: '报告正文', exact: true }).inputValue(), /inputs\.|<!--/);
  assert.ok((await page.locator('#author').boundingBox()).y < (await page.locator('#using').boundingBox()).y);
  await page.getByRole('textbox', { name: '报告正文', exact: true }).fill('# ⟦公司名称⟧\n草稿 ⟦补充说明⟧');
  await page.getByRole('switch', { name: '专家模式' }).click();
  assert.equal(await page.getByLabel('公司名称（必填）').inputValue(), 'Example Company');
  await page.getByRole('switch', { name: '专家模式' }).click();
  assert.match(await page.getByRole('textbox', { name: '报告正文', exact: true }).inputValue(), /草稿/);
  const draftContent = await page.getByRole('textbox', { name: '报告正文', exact: true }).inputValue();
  await page.getByRole('textbox', { name: '报告正文', exact: true }).fill(draftContent + '\n{{unknown.field}}');
  await page.getByRole('button', { name: '预览草稿', exact: true }).click();
  await page.getByText('有一处引用无法使用。请从“引用已有内容”重新选择后预览。', { exact: true }).waitFor();
  assert.equal(await page.getByRole('button', { name: '生成报告', exact: true }).isDisabled(), true);
  await page.getByRole('textbox', { name: '报告正文', exact: true }).fill(draftContent);

  for (const width of [375, 768, 1024, 1440]) {
    await page.setViewportSize({ width, height: 1000 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth), false);
    await page.locator('main').evaluate(el=>el.parentElement.scrollTo(0,0));
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
    await page.getByText('暂时未能确认操作结果。草稿已保留，请先查看列表确认是否已保存，再决定是否重试。', { exact: true }).waitFor();
    assert.doesNotMatch(await page.locator('body').innerText(), /Controlled temporary failure/);
    assert.equal(await page.locator('#mode').isDisabled(), false);
    assert.equal(await page.locator('#content').inputValue(), expectedDraft);
  } finally { await page.unroute('**/api/templates/*', failSave); }
  await page.getByRole('switch', { name: '专家模式' }).click();
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
  assert.equal(await page.getByRole('switch', {name:'专家模式'}).isChecked(),false, 'ordinary preference must survive reload');
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
  await page.locator('#mode').click();
  const pendingUpload = await holdMutation('POST', '**/api/reports/upload');
  try {
    await page.locator('#file').setInputFiles({ name: 'pending-upload.md', mimeType: 'text/markdown', buffer: Buffer.from('# Uploaded after waiting\n\n- First item\n- **Bold item**\n\n| Name | Value |\n| --- | --- |\n| Example | 42 |\n\n```js\nconst result = 42;\n```') });
    await pendingUpload.started;
    await assertMutationLocked();
    pendingUpload.release();
    await page.getByText('报告已上传。', { exact: true }).waitFor();
    assert.match(await page.locator('#report-body').innerText(), /Uploaded after waiting/);
  } finally { pendingUpload.release(); await pendingUpload.dispose(); }
  await page.locator('#report-body ul li').first().waitFor();
  assert.equal(await page.locator('#report-body ul li').count(), 2);
  assert.equal(await page.locator('#report-body strong').innerText(), 'Bold item');
  assert.equal(await page.locator('#report-body table tbody td').last().innerText(), '42');
  assert.match(await page.locator('#report-body pre code').innerText(), /const result = 42;/);
  let deleteRequests=0;
  const countDelete=request=>{if(request.method()==='DELETE')deleteRequests++};
  page.on('request',countDelete);
  await page.getByRole('button', { name: '删除报告', exact: true }).click();
  await page.getByRole('alertdialog').waitFor();
  assert.equal(await page.locator('#workspace').isDisabled(), false, 'confirmation must precede mutation locking');
  await page.getByRole('alertdialog').getByRole('button',{name:'取消',exact:true}).click();
  await page.getByRole('alertdialog').waitFor({state:'hidden'});
  assert.equal(deleteRequests,0,'cancelling confirmation must not write');
  assert.equal(await page.locator('#reading').isVisible(),true);
  const pendingDelete = await holdMutation('DELETE', '**/api/reports/*');
  try {
    await page.getByRole('button', { name: '删除报告', exact: true }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: '删除', exact: true }).click();
    await pendingDelete.started;
    await assertMutationLocked();
    pendingDelete.release();
    await page.getByText('已删除。', { exact: true }).waitFor();
  } finally { pendingDelete.release(); await pendingDelete.dispose(); }
  assert.equal(deleteRequests,1,'confirmed deletion must send exactly one request');
  page.off('request',countDelete);
  assert.equal(await page.locator('#mode').isDisabled(), false);
  // Make a reusable format using only the visible business controls.
  await page.getByRole('button', { name: '使用已有格式', exact: true }).click();
  await page.getByRole('button', { name: '新建格式', exact: true }).click();
  await page.getByLabel('名称', { exact: true }).fill('每周工作总结');
  assert.equal(await page.getByLabel('搜索全部报告或格式').inputValue(), '');
  await page.getByRole('textbox', { name: '报告正文', exact: true }).fill('# 本周进展\n');
  await assertRefreshKeepsWork('#content', '# 本周进展\n');
  await page.getByLabel('新填写项的名称', { exact: true }).fill('本周完成的工作');
  await page.getByRole('button', { name: '添加到正文', exact: true }).click();
  assert.match(await page.locator('#content').inputValue(), /⟦本周完成的工作⟧/);
  assert.doesNotMatch(await page.locator('#content').inputValue(), /inputs\.|field_\d|<!--/);
  await page.getByLabel('选择内容', { exact: true }).selectOption({ label: '指定报告' });
  await page.getByLabel('选择报告', { exact: true }).selectOption({ label: 'Report 00' });
  await page.getByRole('button', { name: '加入正文', exact: true }).click();
  assert.match(await page.locator('#content').inputValue(), /《Report 00》正文/);
  await page.getByLabel('新填写项的名称', { exact: true }).fill('临时填写项');
  await page.getByRole('button', { name: '添加到正文', exact: true }).click();
  await page.locator('.field-control').nth(1).getByRole('button', { name: '移除填写项', exact: true }).click();
  assert.doesNotMatch(await page.locator('#content').inputValue(), /临时填写项/);
  await page.getByLabel('本周完成的工作（必填）').fill('完成体验走查');
  await page.getByRole('switch', { name: '专家模式' }).click();
  await page.getByRole('switch', { name: '专家模式' }).click();
  assert.equal(await page.getByLabel('本周完成的工作（必填）').inputValue(), '完成体验走查');
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await page.getByText('已保存。', { exact: true }).waitFor();
  await page.getByRole('button', { name: '预览报告', exact: true }).click();
  await page.waitForFunction(() => !document.getElementById('generate').disabled);
  assert.match(await page.locator('#preview').innerText(), /完成体验走查/);
  await page.screenshot({ path: path.join(artifactDir, 'business-format.png'), fullPage: true });
  await page.getByRole('button', { name: '生成报告', exact: true }).click();
  await page.getByText('报告已生成并保存。', { exact: true }).waitFor();
  await page.goto(base + '?report=not_found');
  await page.locator('#message.error').waitFor();
  assert.equal(await page.locator('#reading').isVisible(), false);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ status: 'passed', deepLink, screenshots: artifactDir, checks: ['ordinary form', 'optional field', 'preview/generation', 'draft roundtrip', 'deep link reload', 'download', 'history page 2', '404', 'four viewport widths', 'delayed save/generate/upload/delete', 'save failure unlock', 'shared Markdown lists/tables/bold/code', 'delete cancel/confirm', 'theme preference reload'] }));
} finally { await browser.close(); }
