import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import vm from 'node:vm';

const context = vm.createContext({});
vm.runInContext(await readFile(new URL('../web/authoring.js', import.meta.url), 'utf8'), context);
const original = '<!-- input: company | 公司名称 | required -->\n# {{inputs.company}}\nUser source: `{{inputs.keep}}`\n```js\nconst value = "{{inputs.example}}";\n```\n';
context.original = original;
assert.equal(vm.runInContext('new FormatDocument(original).serialize(new FormatDocument(original).visible)', context), original);
const edited = vm.runInContext('(() => { const doc = new FormatDocument(original); return doc.serialize(doc.visible + "追加正文"); })()', context);
assert.equal(edited, original + '追加正文');
assert.match(vm.runInContext('new FormatDocument(original).visible', context), /`\{\{inputs.keep\}\}`/);
const field = vm.runInContext('(() => { const doc = new FormatDocument("# 摘要\\n"); return doc.serialize(doc.visible + doc.addField("本周进展", true)); })()', context);
assert.match(field, /<!-- input: field_1 \| 本周进展 \| required -->/);
assert.match(field, /\{\{inputs.field_1\}\}/);
assert.equal(vm.runInContext('financeError(503, "private failure", "POST")', context), '暂时未能确认操作结果。草稿已保留，请先查看列表确认是否已保存，再决定是否重试。');
console.log('Readable format editing preserves original text and code.');
