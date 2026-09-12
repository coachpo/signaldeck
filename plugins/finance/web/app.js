'use strict';
const $=id=>document.getElementById(id),size=15,drafts=new Map(),values=new Map(),queries=new Map(),unsavedInputs=new Set();
let tab='reports',expert=false,items=[],selected=null,offset=0,more=false,request=0,previewState=null,reportEditing=false,editor=null;
const sources={agent:'任务生成',compiled:'格式生成',uploaded:'文件上传',external:'手动创建'};
function notice(message,error=false){$('message').textContent=message;$('message').className='message'+(error?' error':'')}
async function api(path,method='GET',body){let response;try{response=await fetch('/api/'+path,{method,headers:body instanceof FormData?{}:{'Content-Type':'application/json'},body:body===undefined?undefined:body instanceof FormData?body:JSON.stringify(body)})}catch{throw new FinanceUiError(financeError(0,'',method))}if(!response.ok){let code='';try{code=(await response.json()).code}catch{}throw new FinanceUiError(financeError(response.status,code,method));}return response.status===204?null:response.json()}
function run(fn){return async(...args)=>{try{notice('');await fn(...args)}catch(error){notice(error instanceof FinanceUiError?error.message:'工作区暂时无法完成此操作。请保留草稿并稍后重试。',true)}}}
let writing=false;
// Keep a write bound to the selected object and submitted draft until it settles.
function mutation(fn){return run(async(...args)=>{if(writing)return;writing=true;$('workspace').disabled=true;$('workspace').setAttribute('aria-busy','true');notice('正在处理，请稍候…');try{await fn(...args)}finally{writing=false;$('workspace').disabled=false;$('workspace').removeAttribute('aria-busy');if($('message').textContent==='正在处理，请稍候…')notice('')}})}
function identity(){return tab+':'+(selected?.id??'new')}
function remember(){if(!$('author').hidden){const draft={name:$('name').value,content:editorContent()};if(selected&&draft.name===selected.name&&draft.content===selected.content)drafts.delete(identity());else drafts.set(identity(),draft);}if(!$('using').hidden)values.set(identity(),{...(values.get(identity())||{}),...inputValues()})}
const {renderMarkdown,confirmDelete}=window.SignalDeckUI;
function editorContent(){return tab==='templates'&&editor?editor.serialize($('content').value):$('content').value}
function content(){return expert&&tab==='templates'?editorContent():selected?.content||''}
function invalidate(){previewState=null;$('generation-help').textContent='';$('generate').disabled=true;$('preview').hidden=true;$('diagnostics').replaceChildren();$('diagnostics').className=''}
const fields=templateFields;
function inputValues(){return Object.fromEntries([...$('inputs').querySelectorAll('[data-input]')].map(el=>[el.dataset.input,el.value]))}
function renderInputs(){const saved=values.get(identity())||{};$('inputs').replaceChildren();for(const field of fields(content())){const label=document.createElement('label'),input=document.createElement('textarea');input.id='input-'+field.name;input.dataset.input=field.name;input.required=field.required;input.value=saved[field.name]||'';input.rows=2;input.className="business-input";label.htmlFor=input.id;label.textContent=field.label+(field.required?'（必填）':'（可选）');input.oninput=()=>{unsavedInputs.add(identity());values.set(identity(),{...(values.get(identity())||{}),...inputValues()});invalidate()};$('inputs').append(label,input)}if(!$('inputs').children.length){const p=document.createElement('p');p.textContent='此格式无需填写业务信息。';$('inputs').append(p)}}
function renderList(){const list=$('list');list.replaceChildren();for(const item of items){const button=document.createElement('button');button.className='entry'+(selected?.id===item.id?' active':'');const title=document.createElement('strong'),meta=document.createElement('small');title.textContent=reportName(item);meta.textContent=(sources[item.source]||'报告格式')+' · '+new Date(item.createdAt).toLocaleString();button.append(title,meta);button.onclick=()=>{remember();selected=item;reportEditing=false;invalidate();show();if(tab==='reports')history.replaceState(null,'','?report='+encodeURIComponent(item.slug))};list.append(button)}if(!items.length)list.textContent='没有符合条件的内容。';$('previous').disabled=offset===0;$('next').disabled=!more;$('page').textContent='第 '+(offset/size+1)+' 页'}
async function load(){const ticket=++request;let rows;if(tab==='reports'){const params=new URLSearchParams({limit:String(size+1),offset:String(offset),sort:$('sort').value});for(const [name,id] of [['q','search'],['source','source'],['ticker','ticker'],['tag','tag'],['reviewType','review-type']])if($(id).value)params.set(name,$(id).value);rows=await api('reports?'+params)}else{rows=await api('templates');const query=$('search').value.toLowerCase();rows=rows.filter(x=>(x.name+' '+x.content).toLowerCase().includes(query));rows.sort((a,b)=>$('sort').value==='name'?a.name.localeCompare(b.name):$('sort').value==='oldest'?a.id-b.id:b.id-a.id);rows=rows.slice(offset,offset+size+1)}if(ticket!==request)return;more=rows.length>size;items=rows.slice(0,size);renderList()}
function show(){for(const id of ['reading','using','author'])$(id).hidden=true;$('blank').hidden=!!selected||(expert&&drafts.has(identity()));$('new').hidden=!expert;$('new').textContent=tab==='templates'?'新建格式':'新建报告';$('upload').hidden=!(expert&&tab==='reports');for(const id of ['source','ticker','tag','review-type'])$(id).hidden=tab!=='reports';document.querySelectorAll('[data-tab]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.tab===tab)));if(!selected&&!drafts.has(identity()))return;
if(tab==='reports'&&!reportEditing&&selected){$('reading').hidden=false;$('report-title').textContent=reportName(selected);renderMarkdown($('report-body'),selected.content);$('report-meta').textContent=(sources[selected.source]||'已保存报告')+' · 创建 '+new Date(selected.createdAt).toLocaleString()+' · 更新 '+new Date(selected.updatedAt).toLocaleString();renderProvenance(selected);const missing=selected.content.match(/\[(?:Missing|Unknown|Invalid|Circular)[^\]]*\]/g)||[];$('report-missing').hidden=!missing.length;$('report-missing').textContent='这份报告中仍有未完成的引用，相关内容尚不能确认。请核对正文并重新选择所需来源。';$('edit-report').hidden=!expert||selected.source==='agent';$('delete-report').hidden=!expert||selected.source==='agent';
}else if(expert){$('author').hidden=false;const draft=drafts.get(identity())||selected||{name:'',content:''};$('name').value=draft.name;editor=tab==='templates'?new FormatDocument(draft.content):null;$('content').value=editor?editor.visible:draft.content;if(editor)renderFieldControls();$('name').readOnly=tab==='reports'&&!!selected;$('name').maxLength=tab==='reports'?200:100;$('author-title').textContent=tab==='templates'?'制作报告格式':'编辑报告';$('delete').hidden=!selected||tab!=='templates';$('author-preview').hidden=tab!=='templates';document.querySelector('#author aside').hidden=tab!=='templates';$('draft-note').textContent='切换模式和条目会保留本页草稿。刷新或关闭前请先保存。';if(tab==='templates'){$('using').hidden=false;$('format-title').textContent='试用这个格式';renderInputs()}
}else if(selected){$('using').hidden=false;$('format-title').textContent=selected.name;renderInputs()}else{$('blank').hidden=false;$('blank').textContent='有一份未保存的专家草稿。切回专家模式继续制作。'}renderList()}
const shell=window.SignalDeckUI.mountShell({title:'报告',expertDisabled:()=>writing,onExpertChange(next){remember();expert=next;reportEditing=false;invalidate();show()}});
expert=shell.expert;
show();
for(const button of document.querySelectorAll('[data-tab]'))button.onclick=run(async()=>{remember();queries.set(tab,$('search').value);tab=button.dataset.tab;$('search').value=queries.get(tab)||'';selected=null;offset=0;reportEditing=false;invalidate();history.replaceState(null,'',location.pathname);show();await load();if(tab==='templates')await loadReferences()});
$('filters').onsubmit=run(async event=>{event.preventDefault();offset=0;await load()});$('previous').onclick=run(async()=>{offset=Math.max(0,offset-size);await load()});$('next').onclick=run(async()=>{offset+=size;await load()});
$('new').onclick=()=>{remember();selected=null;reportEditing=true;drafts.set(identity(),drafts.get(identity())||{name:'',content:''});invalidate();show()};$('name').oninput=remember;$('content').oninput=()=>{remember();values.set(identity(),{...(values.get(identity())||{}),...inputValues()});invalidate();renderInputs()};
async function preview(){if(!$('use-form').reportValidity())return;const source=content(),inputs=inputValues();notice('正在生成预览，请稍候…');const result=await api('templates/compile','POST',{content:source,inputs});if(source!==content()||JSON.stringify(inputs)!==JSON.stringify(inputValues()))return;const errors=result.compiled.match(/\[(?:Missing|Unknown|Invalid|Circular)[^\]]*\]/g)||[];renderMarkdown($('preview'),result.compiled.replace(/\[(?:Missing|Unknown|Invalid|Circular)[^\]]*\]/g, marker=>'【'+compileIssue(marker,source)+'】'));$('preview').hidden=false;$('diagnostics').className=errors.length?'warning':'';$('diagnostics').textContent=errors.length?[...new Set(errors.map(marker=>compileIssue(marker,source)))].join(' '):'预览已更新，请核对正文。';previewState={source,inputs,compiled:result.compiled};$('generate').disabled=errors.length>0||!selected||source!==selected.content;$('generation-help').textContent=errors.length?'请先解决上方问题。':!selected||source!==selected.content?'请先保存这个格式，再预览并生成报告。':'确认预览后，生成报告会保存一份新结果。';notice('');}
$('use-form').onsubmit=run(async e=>{e.preventDefault();await preview()});$('author-preview').onclick=run(preview);
$('generate').onclick=mutation(async()=>{if(!previewState||!selected)return;const state=previewState;$('generate').disabled=true;try{const report=await api('reports/compile/'+selected.id,'POST',{inputs:state.inputs,expectedContent:state.source,expectedCompiled:state.compiled});remember();unsavedInputs.delete(identity());tab='reports';selected=report;reportEditing=false;offset=0;invalidate();show();await load();history.replaceState(null,'','?report='+encodeURIComponent(report.slug));notice('报告已生成并保存。')}catch(error){invalidate();throw error}});
$('author').onsubmit=mutation(async event=>{event.preventDefault();const body=selected&&tab==='reports'?{content:editorContent()}:{name:$('name').value,content:editorContent()};const old=identity();const result=await api(tab+(selected?'/'+encodeURIComponent(tab==='reports'?selected.slug:selected.id):''),selected?'PATCH':'POST',body);const savedValues=values.get(old);drafts.delete(old);selected=result;if(savedValues)values.set(identity(),savedValues);reportEditing=false;invalidate();await load();show();notice('已保存。')});
$('edit-report').onclick=()=>{reportEditing=true;show()};
const remove=mutation(async()=>{await api(tab+'/'+encodeURIComponent(tab==='reports'?selected.slug:selected.id),'DELETE');drafts.delete(identity());selected=null;show();await load();notice('已删除。')});
async function confirmRemoval(){
  if(writing||!selected)return;
  const target=selected,currentTab=tab;
  const confirmed=await confirmDelete({title:'删除“'+reportName(target)+'”？',description:'此操作无法撤销。'});
  if(confirmed&&selected===target&&tab===currentTab)await remove();
}
$('delete').onclick=run(confirmRemoval);$('delete-report').onclick=run(confirmRemoval);
$('download').onclick=()=>{if(selected)location.href='/api/reports/'+encodeURIComponent(selected.slug)+'/download'};
function insert(text){const el=$('content');el.setRangeText(text,el.selectionStart,el.selectionEnd,'end');el.dispatchEvent(new Event('input'));el.focus()}
function renderProvenance(report) {
  $('provenance-summary').textContent = report.source === 'agent'
    ? '这份报告由任务生成并保存，保留当时的原始结果。请结合正文中的资料来源核对结论。'
    : report.source === 'compiled' ? '这份报告由已保存的格式生成。引用内容以生成时的结果为准。'
    : report.source === 'uploaded' ? '这份报告来自上传的文件，正文保留原文。' : '这份报告由人工创建并保存。';
  $('provenance').replaceChildren(...reportFacts(report).flatMap(([label, value]) => {
    const name = document.createElement('dt'), detail = document.createElement('dd');
    name.textContent = label; detail.textContent = value; return [name, detail];
  }));
}
function renderReferenceControls() {
  const kind = $('reference-kind').value;
  $('reference-filter').hidden = !['ticker', 'tag'].includes(kind);
  $('reference-report').hidden = kind !== 'specific';
  $('reference-position').hidden = kind !== 'position';
  $('reference-part').hidden = ['all', 'inputs'].includes(kind);
  $('reference-value').placeholder = kind === 'ticker' ? '证券代码' : '标签文字';
}
function renderFieldControls() {
  if (!editor) return;
  $('field-list').replaceChildren();
  $('reference-input').replaceChildren(new Option('使用上方文字', ''));
  for (const [index, field] of editor.fields.entries()) {
    const row = document.createElement('div'); row.className = 'field-control';
    const label = document.createElement('label'), name = document.createElement('input');
    name.value = field.label; name.maxLength = 80; label.textContent = `填写项 ${index + 1} 的名称`; label.append(name);
    const requiredLabel = document.createElement('label'), required = document.createElement('input');
    required.type = 'checkbox'; required.checked = field.required; requiredLabel.append(required, ' 每次都要填写');
    const update = run(async () => {
      const value = name.value.trim();
      if (!value || /[|\n<>]/.test(value)) throw new FinanceUiError('请填写简短的名称，使用文字、数字或常用标点。');
      let raw = editorContent();
      const declaration = `<!-- input: ${field.name} | ${value} | ${required.checked ? 'required' : 'optional'} -->`;
      const previous = [...raw.matchAll(declarationPattern)].find(match => match[1] === field.name);
      raw = previous ? raw.replace(previous[0], declaration) : declaration + '\n' + raw;
      editor = new FormatDocument(raw); $('content').value = editor.visible;
      remember(); invalidate(); renderInputs(); renderFieldControls();
    });
    name.onchange = update; required.onchange = update;
    const add = document.createElement('button'); add.type = 'button'; add.textContent = '再次加入正文';
    add.onclick = () => insert(editor.token(`{{inputs.${field.name}}}`, field.label));
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = '移除填写项';
    remove.onclick = run(async () => {
      const raw = mapProse(editorContent(), text => text.replace(declarationPattern, (match, name) => name === field.name ? '' : match)
        .replace(new RegExp('\\{\\{\\s*inputs\\.' + field.name + '\\s*\\}\\}', 'g'), ''));
      if (templateFields(raw).some(item => item.name === field.name)) throw new FinanceUiError('这项信息仍用于报告引用或正文代码，请先调整相应内容再移除。');
      editor = new FormatDocument(raw); $('content').value = editor.visible;
      remember(); invalidate(); renderInputs(); renderFieldControls();
    });
    row.append(label, requiredLabel, add, remove); $('field-list').append(row);
    $('reference-input').append(new Option(field.label, field.name));
  }
  renderReferenceControls();
}
$('insert-field').onclick=run(async()=>{const label=$('field-label').value.trim();if(!label||/[|\n<>]/.test(label))throw new FinanceUiError('请填写简短的名称，使用文字、数字或常用标点。');if(!editor)return;insert(editor.addField(label,$('field-required').checked));$('field-label').value='';renderFieldControls()});
$('reference-kind').onchange=renderReferenceControls;
$('insert-reference').onclick=run(async()=>{if(!editor)return;const kind=$('reference-kind').value,part=$('reference-field').value;let path='reports';if(kind==='inputs')path='inputs';else if(kind==='latest')path+='.'+'latest';else if(kind==='specific'){if(!$('placeholder').value)throw new FinanceUiError('请先选择一份已有报告。');path+='.'+$('placeholder').value}else if(kind==='position'){const position=Number($('reference-number').value);if(!Number.isInteger(position)||position<1)throw new FinanceUiError('请填写从 1 开始的先后位置。');path+='['+(position-1)+']'}else if(kind==='ticker'||kind==='tag'){const field=$('reference-input').value,value=$('reference-value').value.trim();if(!field&&!value)throw new FinanceUiError('请填写筛选文字，或选择一项本次填写的信息。');if(!field&&/["\n]/.test(value))throw new FinanceUiError('筛选文字不能包含引号或换行。');const argument=field?'inputs.'+field:JSON.stringify(value);path+=kind==='ticker'?'.latest('+argument+')':'.by_tag('+argument+').latest'}if(!['all','inputs'].includes(kind)&&part)path+='.'+part;insert(editor.token('{{'+path+'}}',referenceLabel(path,editor.fields)))});
$('upload').onclick=()=>$('file').click();$('file').onchange=mutation(async()=>{const file=$('file').files[0];if(!file)return;const form=new FormData();form.append('file',file);selected=await api('reports/upload','POST',form);reportEditing=false;await load();show();$('file').value='';notice('报告已上传。')});
window.addEventListener('beforeunload',event=>{remember();if([...drafts.values()].some(draft=>draft.name||draft.content)||[...unsavedInputs].some(key=>Object.values(values.get(key)||{}).some(Boolean))){event.preventDefault();event.returnValue=''}});
async function loadReferences(){const tree=await api('templates/placeholders'),selectedName=$('placeholder').value;$('placeholder').replaceChildren();for(const report of tree.reports){reportLabels.set(report.name,report.label);if(!/^[^.]+$/.test(report.name))continue;const option=new Option(report.label,report.name);$('placeholder').append(option)}if([...$('placeholder').options].some(option=>option.value===selectedName))$('placeholder').value=selectedName}
run(async()=>{const params=new URLSearchParams(location.search),slug=params.get('report'),reportId=params.get('reportId');if(slug||reportId){selected=await api(slug?'reports/'+encodeURIComponent(slug):'reports/by-id/'+encodeURIComponent(reportId));show()}await load();await loadReferences()})();
