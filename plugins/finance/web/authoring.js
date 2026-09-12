'use strict';
class FinanceUiError extends Error {}
// The readable editor retains each existing expression; unchanged drafts round-trip exactly.
const declarationPattern = /<!--\s*input: ([A-Za-z_][A-Za-z0-9_]*)\s*\|\s*([^|\n]+?)\s*\|\s*(required|optional)\s*-->/g;
const reportLabels = new Map();
function templateFields(text) {
  const declared = new Map([...text.matchAll(declarationPattern)].map(match => [match[1], {
    name: match[1], label: match[2], required: match[3] === 'required',
  }]));
  const names = [...declared.keys(), ...[...text.matchAll(/\binputs\.([A-Za-z_][A-Za-z0-9_]*)/g)].map(match => match[1])];
  return [...new Set(names)].map((name, index) => declared.get(name) || {name, label: `填写项 ${index + 1}`, required: true});
}
function mapProse(text, transform) {
  let fence = null;
  return text.match(/[^\n]*(?:\n|$)/g).map(line => {
    const marker = line.match(/^\s*(`{3,}|~{3,})/);
    if (marker) { fence = fence ? null : marker[1][0]; return line; }
    if (fence) return line;
    return line.split(/(`+[^`]*`+)/g).map((part, index) => index % 2 ? part : transform(part)).join('');
  }).join('');
}
class FormatDocument {
  constructor(raw) {
    this.original = raw;
    this.declarations = [];
    mapProse(raw, text => { this.declarations.push(...[...text.matchAll(declarationPattern)].map(match => match[0])); return text; });
    this.fields = templateFields(raw);
    this.tokens = new Map();
    this.visible = mapProse(raw, text => text.replace(new RegExp(declarationPattern.source + '(?:\\r?\\n)?', 'g'), '').replace(/\{\{(.+?)\}\}/g, (expression, path) => {
      const field = this.fields.find(item => path.trim() === 'inputs.' + item.name);
      return this.token(expression, field ? field.label : referenceLabel(path.trim(), this.fields));
    }));
  }
  token(expression, label) {
    for (const [token, value] of this.tokens) if (value === expression) return token;
    let token = `⟦${label}⟧`, index = 2;
    while (this.tokens.has(token) || this.original.includes(token)) token = `⟦${label} ${index++}⟧`;
    this.tokens.set(token, expression);
    return token;
  }
  serialize(visible) {
    if (visible === this.visible) return this.original;
    let raw = visible;
    for (const [token, expression] of this.tokens) raw = mapProse(raw, text => text.split(token).join(expression));
    return this.declarations.join('\n') + (this.declarations.length ? '\n' : '') + raw;
  }
  addField(label, required) {
    let index = 1;
    while (this.fields.some(field => field.name === `field_${index}`)) index++;
    const field = {name: `field_${index}`, label, required};
    this.fields.push(field);
    this.declarations.push(`<!-- input: ${field.name} | ${label} | ${required ? 'required' : 'optional'} -->`);
    return this.token(`{{inputs.${field.name}}}`, label);
  }
}
function referenceLabel(path, fields = []) {
  if (path === 'inputs') return '本次填写的信息';
  if (path === 'reports') return '全部报告列表';
  const value = path.endsWith('.name') ? '名称' : path.endsWith('.created_at') ? '日期' : path.endsWith('.content') ? '正文' : '摘要';
  const argument = path.match(/\((.*?)\)/)?.[1];
  const filter = argument?.startsWith('inputs.') ? fields.find(field => 'inputs.' + field.name === argument)?.label : argument?.replace(/^"|"$/g, '');
  if (path.startsWith('reports.latest')) return `最新报告${value}${filter ? '（证券：' + filter + '）' : ''}`;
  if (path.startsWith('reports.by_tag(')) return `最新报告${value}（标签：${filter || '本次选择'}）`;
  if (path.startsWith('reports[')) return `第 ${Number(path.match(/\[(\d+)\]/)?.[1] || 0) + 1} 份报告${value}`;
  if (path.startsWith('reports.')) {
    const name = path.slice(8).split('.')[0];
    return `${reportLabels.has(name) ? '《' + reportLabels.get(name) + '》' : '指定报告'}${value}`;
  }
  return '待检查的引用';
}
function compileIssue(marker, source) {
  const missing = marker.match(/^\[Missing input: (.+)\]$/);
  if (missing) {
    const field = templateFields(source).find(item => item.name === missing[1]);
    return `请填写${field ? '“' + field.label + '”' : '所需信息'}后重新预览。`;
  }
  if (marker.startsWith('[Circular')) return '报告之间相互引用，无法完成预览。请移除其中一处引用后重试。';
  if (marker.startsWith('[Unknown report:')) return '引用的报告已不可用。请选择另一份报告后重新预览。';
  return '有一处引用无法使用。请从“引用已有内容”重新选择后预览。';
}
function reportName(report) {
  return report.source === 'agent' ? report.name.replace(/_[a-f0-9]{32}$/, '') : report.name;
}
function reportFacts(report) {
  const metadata = report.metadata || {}, analysis = metadata.analysis || {};
  return [
    ['作者', metadata.author], ['说明', metadata.description],
    ['标签', metadata.tags?.join('、')], ['证券代码', analysis.ticker],
    ['研究类型', analysis.reviewType], ['研究日期', analysis.reviewDate],
  ].filter(([, value]) => typeof value === 'string' && value.length);
}
function financeError(status, code, method) {
  const known = {
    preview_changed: '报告格式或引用内容已有变化。请重新预览，核对后再生成报告。',
    immutable_agent_report: '这份报告是任务保存的原始结果，不能更改或删除。可下载正文，或新建报告继续整理。',
    invalid_file_type: '请选择 Markdown 文本文件。',
    file_too_large: '文件过大，请缩小文件后重新上传。',
    invalid_file_encoding: '无法读取这份文件的文字。请将其另存为 UTF-8 文本后重新上传。',
    empty_file: '文件没有正文，请选择包含内容的文件。',
    slug_conflict: '已有同名内容，请换一个名称后保存。',
    validation_error: '请检查名称、正文和必填信息后重试。',
  };
  if (known[code]) return known[code];
  if (status === 404) return '找不到这份内容。请从列表重新选择，或调整查询条件。';
  if (status === 401 || status === 403) return '当前无法访问报告工作区。请检查连接设置后重试。';
  return method === 'GET' ? '报告工作区暂时无法读取。请稍后重试。' : '暂时未能确认操作结果。草稿已保留，请先查看列表确认是否已保存，再决定是否重试。';
}
