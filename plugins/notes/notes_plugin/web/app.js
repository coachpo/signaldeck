'use strict';
class NotesReadError extends Error {}
const $ = id => document.getElementById(id);
const sourceLabel = kind => ({original: '原始资料', derived: '整理结果', unclassified: '来源未分类'})[kind] || '来源未分类';
let generation = 0;
let currentNote = null;
let nextCursor = null;
function url(params) { const value = params.toString(); return location.pathname + (value ? '?' + value : ''); }
function navigate(params) { history.pushState(null, '', url(params)); render(); }
async function read(path, params) {
  const response = await fetch(path + (params ? '?' + params : ''), {headers: {'Accept': 'application/json'}});
  if (!response.ok) throw new NotesReadError(response.status === 404 ? '找不到这条笔记。请返回列表查找其他内容。' : '笔记暂时无法读取，请稍后重试。');
  return response.json();
}
async function showSources(note, params, revision) {
  const ids = note.sourceNoteIds || [];
  $('noteSources').textContent = ids.length ? '正在查找来源标题…' : note.sourceKind === 'derived'
    ? '这份整理结果没有关联原始笔记。请核对正文中的依据后使用。'
    : note.sourceKind === 'original' ? '这是一份原始资料。' : '保存时没有记录资料来源，请结合正文自行核对。';
  if (!ids.length) return;
  const sources = await Promise.allSettled(ids.map(id => read('api/note', new URLSearchParams({id}))));
  if (revision !== generation) return;
  $('noteSources').replaceChildren(...sources.map((result, index) => {
    const row = document.createElement('p');
    const target = new URLSearchParams(params); target.set('noteId', ids[index]);
    const link = document.createElement('a'); link.href = url(target);
    if (result.status === 'fulfilled') link.textContent = result.value.title || '未命名笔记';
    else { row.append('这份来源暂时无法读取，尚不能核对其内容。'); link.textContent = '重新查看来源'; }
    row.append(link); return row;
  }));
}
async function render() {
  const revision = ++generation;
  const params = new URLSearchParams(location.search);
  const noteId = params.get('noteId');
  $('browse').hidden = Boolean(noteId); $('detail').hidden = true;
  for (const control of $('search').elements) control.disabled = true;
  $('search').setAttribute('aria-busy', 'true');
  $('previous').disabled = true; $('next').disabled = true;
  $('status').textContent = '正在读取笔记…';
  currentNote = null; nextCursor = null;
  try {
    if (noteId) {
      const note = await read('api/note', new URLSearchParams({id: noteId}));
      if (revision !== generation) return;
      currentNote = note;
      $('noteTitle').textContent = note.title; $('noteText').textContent = note.text;
      $('noteSourceKind').textContent = sourceLabel(note.sourceKind);
      void showSources(note, params, revision);
      $('noteCollection').textContent = note.collection;
      params.delete('noteId'); $('back').href = url(params);
      $('detail').hidden = false; $('status').textContent = '';
      return;
    }
    const data = await read('api/collections');
    if (revision !== generation) return;
    let collection = params.get('collection') || data.collections[0]?.name || '';
    const collections = [...data.collections];
    if (collection && !collections.some(item => item.name === collection)) collections.push({name: collection, count: 0});
    $('collection').replaceChildren(...collections.map(item => { const option = document.createElement('option'); option.value = item.name; option.textContent = `${item.name} (${item.count})`; return option; }));
    $('includeDerived').value = params.get('includeDerived') === 'true' ? 'true' : 'false';
    $('collection').value = collection; $('query').value = params.get('query') || '';
    $('notes').replaceChildren(); $('previous').disabled = true; $('next').disabled = true; $('page').textContent = '';
    if (!collection) { $('status').textContent = '还没有笔记。保存第一条笔记后，它会显示在这里。'; $('summary').textContent = ''; return; }
    params.set('collection', collection); history.replaceState(null, '', url(params));
    const request = new URLSearchParams({collection, query: params.get('query') || '', limit: '20', includeDerived: $('includeDerived').value});
    const cursors = params.getAll('cursor');
    if (cursors.length) request.set('after', cursors[cursors.length - 1]);
    const result = await read('api/notes', request);
    if (revision !== generation) return;
    nextCursor = result.nextCursor;
    $('notes').replaceChildren(...result.notes.map(note => {
      const link = document.createElement('a'); link.className = 'note';
      const target = new URLSearchParams(params); target.set('noteId', note.id); link.href = url(target);
      const title = document.createElement('h2'); title.textContent = `${note.title} · ${sourceLabel(note.sourceKind)}`;
      const preview = document.createElement('p'); preview.textContent = note.text.slice(0, 220) + (note.text.length > 220 ? '…' : '');
      link.append(title, preview); return link;
    }));
    $('summary').textContent = `本页 ${result.notes.length} 条笔记`;
    $('page').textContent = `第 ${cursors.length + 1} 页`;
    $('previous').disabled = !cursors.length; $('next').disabled = nextCursor === null;
    $('status').textContent = result.notes.length ? '' : '没有找到匹配的笔记。试试其他文字或集合。';
  } catch (error) {
    if (revision !== generation) return;
    $('status').textContent = error instanceof NotesReadError ? error.message : '笔记暂时无法读取，请检查连接后重试。';
    $('notes').replaceChildren(); $('summary').textContent = '';
    const retry = document.createElement('button'); retry.textContent = '重新读取'; retry.onclick = render; $('status').append(retry);
    if (noteId) { params.delete('noteId'); const back = document.createElement('a'); back.href = url(params); back.textContent = ' 返回笔记'; $('status').append(back); }
  } finally {
    if (revision === generation) {
      for (const control of $('search').elements) control.disabled = false;
      $('search').removeAttribute('aria-busy');
    }
  }
}
$('search').addEventListener('submit', event => { event.preventDefault(); navigate(new URLSearchParams({collection: $('collection').value, query: $('query').value, includeDerived: $('includeDerived').value})); });
$('next').addEventListener('click', () => { if (nextCursor === null) return; const params = new URLSearchParams(location.search); params.append('cursor', nextCursor); navigate(params); });
$('previous').addEventListener('click', () => { const params = new URLSearchParams(location.search); const cursors = params.getAll('cursor'); params.delete('cursor'); cursors.slice(0, -1).forEach(cursor => params.append('cursor', cursor)); navigate(params); });
$('copy').addEventListener('click', async () => { if (!currentNote) return; try { await navigator.clipboard.writeText(currentNote.text); $('status').textContent = '正文已复制。'; } catch { $('status').textContent = '浏览器未允许复制，请选择正文后手动复制。'; } });
window.addEventListener('popstate', render);
render();
