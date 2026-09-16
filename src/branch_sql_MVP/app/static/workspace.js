'use strict';
const $=id=>document.getElementById(id), fmt=x=>JSON.stringify(x,null,2);
let workflow=null, current=null, stack=[], selected=null, ensured=false, dirty=false, runId=null, cursor=0, polling=null;
let nodeDirty=false, submitting=false, zoom=1;
let library=[], templates=[], datasets=[], settings={}, records=[], statuses={};
const PROMPT_KEYS=['system_prompt','user_prompt','provider','model','temperature','max_tokens','response_format'];
async function api(path, options){const response=await fetch(path,options);if(!response.ok)throw Error(await response.text());return response.json()}
const json=(method,body)=>({method,headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
function notice(text,error=false){$('notice').textContent=text;$('notice').classList.toggle('error',error)}
function action(fn){return async(...args)=>{try{await fn(...args)}catch(e){notice(e.message,true)}}}
function page(id){document.querySelectorAll('main>section').forEach(el=>el.hidden=el.id!==id);$('title').textContent=id==='editor'?(workflow.name||workflow.id):({pipelines:'Pipelines',datasets:'Dữ liệu & Offline',history:'Lịch sử',settings:'Settings',tools:'Công cụ nâng cao'}[id]);}
function card(name,detail,onclick,chip){const button=document.createElement('button');button.className='card';const title=document.createElement('b'),small=document.createElement('small');title.textContent=name;small.textContent=detail;button.append(title,small);if(chip){const span=document.createElement('span');span.className='chip'+(chip.index?' index':'');span.textContent=chip.text;button.append(span)}button.onclick=action(onclick);return button;}

// --- Pipeline catalog: 8 templates only, no forced "save as copy" ---
async function catalog(){$('templates').replaceChildren(...templates.map(t=>card(t.name||t.id,t.description||(t.kind+' · '+t.nodes.length+' nodes'),()=>openPipeline(t),{index:t.requires_index,text:t.requires_index?'Cần index':'Không cần index'})));}

// Opening a template must never clobber a saved customisation: load the stored
// revision when one exists, and only fall back to the pristine template.
async function openPipeline(template){
  let definition=template, isSaved=false;
  if(template.kind!=='offline'){
    // Look the id up in the list instead of probing it: an uncustomised pipeline
    // is the normal case and must not show up as a 404 in the server log.
    const stored=(await api('/studio/workflows')).find(w=>w.id===template.id);
    if(stored){definition=stored;isSaved=true}
  }
  open(definition,isSaved);
  if(isSaved)notice('Đã mở cấu hình đã lưu (revision '+definition.revision+').');
}

function open(value,isSaved=false){clearTimeout(polling);runId=null;records=[];cursor=0;statuses={};$('events').replaceChildren();$('answer').textContent='';$('sql').textContent='';$('table').replaceChildren();$('run-error').hidden=true;$('node-output').textContent='';$('run').disabled=false;$('cancel').disabled=true;nodeDirty=false;ensured=isSaved;dirty=false;workflow=structuredClone(value);current=workflow;stack=[];selected=null;$('pipeline-select').value=workflow.id;$('pipeline-select').hidden=workflow.kind==='offline';$('dataset-control').hidden=workflow.kind==='offline';$('mode-control').hidden=workflow.kind==='offline';$('revert').hidden=!isSaved;$('saved-chip').hidden=!isSaved;page('editor');closeNode();renderDatasetSelect();zoom=1;draw();openView();}
function graph(){return current}

// A saved workflow id is only ever created lazily, under the template's own
// id, right before an action needs it in the store (run / node test). The
// user never sees or edits a name.
async function ensureSaved(){
  if(nodeDirty&&!apply())throw Error('Sửa lỗi cấu hình node trước khi chạy.');
  if(ensured&&!dirty)return workflow;
  if(!ensured){
    try{const result=await api('/studio/workflows',json('POST',workflow));workflow.revision=result.revision;ensured=true;dirty=false;$('saved-chip').hidden=false;$('revert').hidden=false;return workflow}
    catch(e){ensured=true}
  }
  // The stored revision we hold is the optimistic-lock token; a mismatch means
  // somebody else changed the pipeline and we must not overwrite them.
  try{
    const result=await api('/studio/workflows/'+encodeURIComponent(workflow.id),json('PUT',workflow));
    workflow.revision=result.revision;dirty=false;$('saved-chip').hidden=false;$('revert').hidden=false;return workflow;
  }catch(e){
    throw Error('Cấu hình đã bị thay đổi ở nơi khác — mở lại pipeline để tải bản mới nhất. ('+e.message+')');
  }
}

// --- Canvas: Dify-style cards; bounded_loop/foreach are drawn as containers ---
// The whole pipeline, subgraphs included, is always drawn. `stack`/`current`
// only track which subgraph the selected node lives in.
const SVG='http://www.w3.org/2000/svg', NODE_W=240, NODE_H=60, GAP_X=64, GAP_Y=28, HEAD=60, PAD=28, LOOP_BAND=46, MARGIN=40, INNER_MARGIN=8;
const KINDS={start:['▶','#12b76a','Bắt đầu'],llm:['✦','#6172f3','LLM'],context_builder:['☰','#0ba5ec','Dựng ngữ cảnh'],schema_link:['⌗','#0ba5ec','Liên kết schema'],value_link:['≡','#0ba5ec','Liên kết giá trị'],retrieval:['⌕','#0ba5ec','Truy hồi tài liệu'],example_retrieval:['⌕','#0ba5ec','Truy hồi ví dụ SQL'],events:['◈','#7a5af8','Sự kiện'],evidence_filter:['⧩','#7a5af8','Lọc bằng chứng'],sql_executor:['⛁','#f79009','Thực thi SQL'],branch:['⑂','#ee46bc','Rẽ nhánh'],condition:['⑂','#ee46bc','Điều kiện'],merge:['⤚','#667085','Gộp nhánh'],candidate:['◇','#15b79e','Ứng viên SQL'],candidate_select:['◆','#15b79e','Chọn ứng viên'],strategies:['⋮','#15b79e','Chiến lược sinh'],answer_guard:['✓','#f04438','Kiểm tra kết quả'],result:['■','#475467','Kết quả'],output:['■','#475467','Đầu ra'],passthrough:['→','#667085','Chuyển tiếp'],bounded_loop:['↻','#2e90fa','Vòng lặp'],foreach:['↻','#2e90fa','Lặp qua danh sách'],graph_prepare:['⬡','#7a5af8','GraphRAG · chuẩn bị'],graph_resolve:['⬡','#7a5af8','GraphRAG · hợp nhất'],graph_write:['⬡','#7a5af8','GraphRAG · ghi']};
function kindOf(type){return KINDS[type]||(type.startsWith('offline_')?['⚙','#667085','Offline · '+type.slice(8)]:['•','#667085',type])}
let lastLayout=null;

// Layered left-to-right layout. Containers are sized from their own body
// layout first, so parents reserve exactly the room their children need.
function layout(def,margin=MARGIN){
  const size={},inner={};
  for(const n of def.nodes){
    if(n.config.body){const child=layout(n.config.body,INNER_MARGIN);inner[n.id]=child;size[n.id]={w:Math.max(child.width+PAD*2,NODE_W+40),h:HEAD+child.height+LOOP_BAND}}
    else size[n.id]={w:NODE_W,h:NODE_H};
  }
  const level=Object.fromEntries(def.nodes.map(n=>[n.id,0]));
  for(let i=0;i<def.nodes.length;i++){let changed=false;for(const e of def.edges){if(level[e.source]+1>level[e.target]){level[e.target]=level[e.source]+1;changed=true}}if(!changed)break}
  const columns=[];for(const n of def.nodes)(columns[level[n.id]]??=[]).push(n.id);
  const heights=columns.map(ids=>ids.reduce((sum,id)=>sum+size[id].h,0)+GAP_Y*(ids.length-1));
  const tallest=Math.max(0,...heights), pos={};
  let x=margin;
  columns.forEach((ids,l)=>{
    // Order each column by where its parents sit, to keep edges from crossing.
    const centre=id=>{const ys=def.edges.filter(e=>e.target===id&&pos[e.source]).map(e=>pos[e.source].y+pos[e.source].h/2);return ys.length?ys.reduce((a,b)=>a+b,0)/ys.length:1e9};
    if(l>0)ids.sort((a,b)=>centre(a)-centre(b));
    const width=Math.max(...ids.map(id=>size[id].w));
    let y=margin+(tallest-heights[l])/2;
    for(const id of ids){pos[id]={x:x+(width-size[id].w)/2,y,...size[id]};y+=size[id].h+GAP_Y}
    x+=width+GAP_X;
  });
  return {pos,inner,width:x-GAP_X+margin,height:tallest+margin*2};
}

function el(tag,className,text){const node=document.createElement(tag);if(className)node.className=className;if(text!=null)node.textContent=text;return node}
function svgEl(tag,attrs){const node=document.createElementNS(SVG,tag);for(const [k,v] of Object.entries(attrs))node.setAttribute(k,v);return node}
function isSelected(path,id){return id===selected&&path.join('/')===scopeKey()}

function draw(){
  if(!workflow)return;
  const canvas=$('canvas');canvas.replaceChildren();
  lastLayout=layout(workflow);
  canvas.style.width=lastLayout.width+'px';canvas.style.height=lastLayout.height+'px';
  const defs=svgEl('svg',{width:0,height:0,style:'position:absolute'});
  defs.innerHTML='<defs><marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#98a2b3"/></marker><marker id="arrow-on" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#5866df"/></marker><marker id="arrow-loop" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" fill="#2e90fa"/></marker></defs>';
  canvas.append(defs);
  renderGraph(canvas,workflow,lastLayout,[]);
  applyZoom();
}

function renderGraph(host,def,box,path){
  const prefix=path.join('/');
  const edges=svgEl('svg',{class:'edges',width:box.width,height:box.height});
  const anchor=(id,side)=>{const p=box.pos[id],y=p.y+(def.nodes.find(n=>n.id===id).config.body?HEAD/2:p.h/2);return {x:side==='out'?p.x+p.w:p.x,y}};
  for(const e of def.edges){
    if(!box.pos[e.source]||!box.pos[e.target])continue;
    const a=anchor(e.source,'out'),b=anchor(e.target,'in'),dx=Math.max(36,(b.x-a.x)/2);
    const on=isSelected(path,e.source)||isSelected(path,e.target);
    edges.append(svgEl('path',{d:`M${a.x},${a.y} C${a.x+dx},${a.y} ${b.x-dx},${b.y} ${b.x-2},${b.y}`,fill:'none',stroke:on?'#5866df':'#b0b8c4','stroke-width':on?2.2:1.6,'marker-end':on?'url(#arrow-on)':'url(#arrow)',...(e.condition?{'stroke-dasharray':'5 4'}:{})}));
    if(e.condition){const label=el('span','edge-label',e.condition);label.style.left=(a.x+b.x)/2+'px';label.style.top=(a.y+b.y)/2+'px';host.append(label)}
  }
  host.append(edges);
  const incoming=new Set(def.edges.map(e=>e.target)),outgoing=new Set(def.edges.map(e=>e.source));
  for(const n of def.nodes){
    const p=box.pos[n.id],state=statuses[prefix+'|'+n.id];
    const card=nodeCard(n,path,state,incoming.has(n.id),outgoing.has(n.id));
    if(!n.config.body){card.style.left=p.x+'px';card.style.top=p.y+'px';card.style.width=p.w+'px';card.style.height=p.h+'px';host.append(card);continue}
    // Loop/foreach: a container holding its own subgraph plus a loop-back arrow.
    const group=el('div','group'+(isSelected(path,n.id)?' selected':'')+(state==='failed'?' failed':''));
    Object.assign(group.style,{left:p.x+'px',top:p.y+'px',width:p.w+'px',height:p.h+'px'});
    card.style.width=p.w+'px';card.style.height=HEAD+'px';group.append(card);
    const child=box.inner[n.id],body=el('div','group-body');
    Object.assign(body.style,{left:(p.w-child.width)/2+'px',top:HEAD+'px',width:child.width+'px',height:child.height+'px'});
    renderGraph(body,n.config.body,child,[...path,n.id]);group.append(body);
    const band=svgEl('svg',{class:'loop-band',width:p.w,height:LOOP_BAND}),w=p.w,y=LOOP_BAND/2+4;
    band.append(svgEl('path',{d:`M${w-24},0 L${w-24},${y-10} Q${w-24},${y} ${w-34},${y} L34,${y} Q24,${y} 24,${y-10} L24,2`,fill:'none',stroke:'#2e90fa','stroke-width':1.6,'stroke-dasharray':'5 4','marker-end':'url(#arrow-loop)'}));
    group.append(band);
    const label=el('span','edge-label loop-label',loopText(n));label.style.left=p.w/2+'px';label.style.top=(p.h-LOOP_BAND/2+4)+'px';group.append(label);
    host.append(group);
  }
}
function loopText(n){
  if(n.type==='bounded_loop')return '↻ Lặp tối đa '+n.config.max_iterations+' lần';
  const max=n.config.max_items;return '↻ Mỗi phần tử'+(max&&max<1000?' · tối đa '+max:'');
}
function nodeCard(n,path,state,hasIn,hasOut){
  const [icon,color,kind]=kindOf(n.type);
  const card=el('button','node'+(isSelected(path,n.id)?' selected':'')+(state?' '+state:''));
  card.dataset.id=n.id;card.style.setProperty('--kind',color);
  const text=el('span','node-text');text.append(el('b',null,n.label),el('small',null,n.config.body?kind+' · '+n.config.body.nodes.length+' bước':kind));
  card.append(el('span','node-icon',icon),text,el('span','node-status',state==='completed'?'✓':state==='failed'?'!':''));
  if(hasIn)card.append(el('i','handle in'));if(hasOut)card.append(el('i','handle out'));
  card.title=n.id+' · '+n.type;
  card.onclick=action(event=>{event.stopPropagation();selectNode(path,n.id)});
  return card;
}
function focusScope(path){stack=[];current=workflow;for(const id of path){const parent=current.nodes.find(n=>n.id===id);stack.push(current);current=parent.config.body}}
function selectNode(path,id){if(nodeDirty&&selected&&!apply())return;focusScope(path);inspect(id);draw()}

function applyZoom(){if(!lastLayout)return;$('canvas').style.transform=`scale(${zoom})`;$('stage').style.width=lastLayout.width*zoom+'px';$('stage').style.height=lastLayout.height*zoom+'px';$('zoom-reset').textContent=Math.round(zoom*100)+'%';minimap()}
// Pipelines are much wider than tall; a full fit would make labels unreadable,
// so opening keeps text legible, starts at the first node and relies on the minimap.
function openView(){
  if(!lastLayout)return;const viewport=$('viewport');
  const full=Math.min((viewport.clientWidth-48)/lastLayout.width,(viewport.clientHeight-48)/lastLayout.height);
  zoom=Math.max(.85,Math.min(1,full));
  applyZoom();viewport.scrollLeft=0;viewport.scrollTop=Math.max(0,(lastLayout.height*zoom-viewport.clientHeight)/2);minimap();
}
function minimap(){
  const map=$('minimap');if(!lastLayout||!map)return;
  const viewport=$('viewport'),W=180,ratio=W/lastLayout.width,H=Math.max(24,lastLayout.height*ratio);
  map.style.width=W+'px';map.style.height=H+'px';map.replaceChildren();
  (function blocks(def,box,ox,oy){for(const n of def.nodes){const p=box.pos[n.id],b=el('i','mini-node'+(n.config.body?' mini-group':''));
    Object.assign(b.style,{left:(ox+p.x)*ratio+'px',top:(oy+p.y)*ratio+'px',width:Math.max(2,p.w*ratio)+'px',height:Math.max(2,p.h*ratio)+'px',background:n.config.body?'':kindOf(n.type)[1]});map.append(b);
    if(n.config.body){const c=box.inner[n.id];blocks(n.config.body,c,ox+p.x+(p.w-c.width)/2,oy+p.y+HEAD)}}})(workflow,lastLayout,0,0);
  const view=el('i','mini-view');
  Object.assign(view.style,{left:viewport.scrollLeft/zoom*ratio+'px',top:viewport.scrollTop/zoom*ratio+'px',width:Math.min(W,viewport.clientWidth/zoom*ratio)+'px',height:Math.min(H,viewport.clientHeight/zoom*ratio)+'px'});
  map.append(view);
}
function scale(v,focus){
  const viewport=$('viewport'),previous=zoom;zoom=Math.max(.2,Math.min(1.6,v));
  // Keep the point under the cursor (or the centre) fixed while zooming.
  const fx=focus?.x??viewport.clientWidth/2,fy=focus?.y??viewport.clientHeight/2;
  const cx=(viewport.scrollLeft+fx)/previous,cy=(viewport.scrollTop+fy)/previous;
  applyZoom();viewport.scrollLeft=cx*zoom-fx;viewport.scrollTop=cy*zoom-fy;
}
function fit(){
  if(!lastLayout)return;const viewport=$('viewport');
  zoom=Math.max(.2,Math.min(1,(viewport.clientWidth-48)/lastLayout.width,(viewport.clientHeight-48)/lastLayout.height));
  applyZoom();viewport.scrollLeft=0;viewport.scrollTop=0;
}
$('zoom-in').onclick=()=>scale(zoom+.1);$('zoom-out').onclick=()=>scale(zoom-.1);$('zoom-reset').onclick=()=>scale(1);$('zoom-fit').onclick=fit;
$('viewport').addEventListener('wheel',event=>{if(!event.ctrlKey&&!event.metaKey)return;event.preventDefault();const rect=$('viewport').getBoundingClientRect();scale(zoom*(event.deltaY<0?1.1:1/1.1),{x:event.clientX-rect.left,y:event.clientY-rect.top})},{passive:false});
// Drag the empty background to pan, like a canvas editor.
(()=>{let drag=null;const viewport=$('viewport');
  viewport.addEventListener('mousedown',event=>{if(event.button!==0||event.target.closest('.node'))return;drag={x:event.clientX,y:event.clientY,left:viewport.scrollLeft,top:viewport.scrollTop};viewport.classList.add('panning')});
  window.addEventListener('mousemove',event=>{if(!drag)return;viewport.scrollLeft=drag.left-(event.clientX-drag.x);viewport.scrollTop=drag.top-(event.clientY-drag.y)});
  window.addEventListener('mouseup',()=>{drag=null;viewport.classList.remove('panning')});
  window.addEventListener('resize',()=>{if(!$('editor').hidden)applyZoom()});
  viewport.addEventListener('scroll',minimap);
  // Click the minimap to jump there.
  $('minimap').addEventListener('mousedown',event=>{if(!lastLayout)return;const rect=$('minimap').getBoundingClientRect(),ratio=rect.width/lastLayout.width;
    viewport.scrollLeft=(event.clientX-rect.left)/ratio*zoom-viewport.clientWidth/2;viewport.scrollTop=(event.clientY-rect.top)/ratio*zoom-viewport.clientHeight/2;event.stopPropagation()});
})();

// --- Right panel: question/settings by default, node config+debug when a node is selected ---
function closeNode(){if(nodeDirty&&selected&&!apply())return false;selected=null;nodeDirty=false;stack=[];current=workflow;const offline=workflow?.kind==='offline';$('node-panel').hidden=true;$('question-panel').hidden=offline;$('offline-panel').hidden=!offline;draw();return true}
$('close-node').onclick=()=>closeNode();

function inspect(id){if(nodeDirty&&selected&&!apply())return;selected=id;nodeDirty=false;const node=graph().nodes.find(n=>n.id===id);if(!node)return;
  $('question-panel').hidden=true;$('offline-panel').hidden=true;$('node-panel').hidden=false;
  $('node-title').textContent=node.label;$('node-label').value=node.label;
  const scopeLabels=scopePath().map(id=>stack.flatMap(g=>g.nodes).find(n=>n.id===id)?.label||id);
  $('node-scope').textContent=kindOf(node.type)[2]+(scopeLabels.length?' · bên trong '+scopeLabels.join(' › '):'');
  // Advanced JSON never repeats what the typed fields already own.
  const hidden=node.type==='llm'?['body',...PROMPT_KEYS]:['body'];
  $('config').value=fmt(Object.fromEntries(Object.entries(node.config).filter(([key])=>!hidden.includes(key))));
  $('inputs').value=fmt(node.inputs);renderInputSummary(node);
  $('llm-fields').hidden=node.type!=='llm';
  if(node.type==='llm'){
    $('system-prompt').value=node.config.system_prompt||'';$('user-prompt').value=node.config.user_prompt||'';
    $('llm-provider').value=node.config.provider||'';$('llm-model').value=node.config.model||'';
    $('llm-temperature').value=node.config.temperature??'';$('llm-max-tokens').value=node.config.max_tokens??'';
    $('llm-response-format').value=node.config.response_format||'text';
    $('inheritance').textContent='Kế thừa workspace: '+settings.api.provider+' / '+settings.api.model;
  }
  showInvocations();
  const latest=invocationEvents('node_started').at(-1);
  $('test-input').value=fmt(latest?.inputs||{});
  inspectorTab('config');
}
function renderInputSummary(node){const root=$('input-summary');root.replaceChildren();const entries=Object.entries(node.inputs);if(!entries.length){root.append(document.createElement('p')).textContent='Không có input.';return}
  const list=document.createElement('div');
  for(const [key,ref] of entries){const row=document.createElement('p');row.textContent=ref.node_id?`${key} ← ${ref.node_id}.${ref.output}`:`${key} = ${JSON.stringify(ref.value)}`;list.append(row)}
  root.append(list);
}
function apply(){if(!selected)return true;const node=graph().nodes.find(n=>n.id===selected);let extra={};try{extra=JSON.parse($('config').value)}catch(e){notice('Cấu hình JSON không hợp lệ: '+e.message,true);return false}
  let inputs;try{inputs=JSON.parse($('inputs').value)}catch(e){notice('Input JSON không hợp lệ: '+e.message,true);return false}
  node.config={...extra,...(node.config.body?{body:node.config.body}:{})};
  node.inputs=inputs;
  node.label=$('node-label').value;
  if(node.type==='llm'){
    node.config.system_prompt=$('system-prompt').value;node.config.user_prompt=$('user-prompt').value;
    node.config.response_format=$('llm-response-format').value;
    for(const [key,id] of [['provider','llm-provider'],['model','llm-model']]){if($(id).value)node.config[key]=$(id).value;else delete node.config[key]}
    for(const [key,id,cast] of [['temperature','llm-temperature',Number],['max_tokens','llm-max-tokens',Number]]){if($(id).value!=='')node.config[key]=cast($(id).value);else delete node.config[key]}
  }
  nodeDirty=false;dirty=true;draw();return true
}

async function run(){if(submitting)return;
  if(workflow.kind==='online'){const problem=datasetProblem(selectedDataset());if(problem){updateDatasetStatus();throw Error(problem)}}
  submitting=true;$('run').disabled=true;
  try{
    await ensureSaved();
    records=[];cursor=0;statuses={};$('events').replaceChildren();$('answer').textContent='';$('sql').textContent='';$('table').replaceChildren();$('run-error').hidden=true;draw();
    const inputs={question:$('question').value,mode:$('mode').value};
    const launchedWorkflow=workflow;
    const row=await api('/studio/runs',json('POST',{workflow_id:workflow.id,revision:workflow.revision,inputs,api_key:apiKey(),dataset_id:workflow.kind==='offline'?null:($('dataset').value||null)}));
    if(workflow!==launchedWorkflow)return;
    runId=row.id;$('cancel').disabled=false;watch();
  }catch(error){$('run').disabled=false;throw error}
  finally{submitting=false}
}

async function watch(){clearTimeout(polling);const watching=runId;if(!watching)return;
  try{
    const events=await api(`/studio/runs/${watching}/events?after=${cursor}`);
    if(runId!==watching)return;
    let touched=false;
    for(const event of events){
      cursor=Math.max(cursor,event.sequence);records.push(event);
      const button=document.createElement('button');button.textContent=`${event.sequence} · ${event.scope||''} ${event.node_id||''} ${event.type}`;
      button.onclick=()=>{$('node-output').textContent=fmt(event);if(!$('node-panel').hidden)inspectorTab('output')};
      $('events').append(button);
      if(event.node_id&&event.type.startsWith('node_')){
        statuses[scopeOf(event)+'|'+event.node_id]=event.type==='node_started'?'running':event.type.replace('node_','');
        touched=true;
      }
    }
    if(touched)draw();
    const row=await api('/studio/runs/'+watching);
    if(runId!==watching)return;
    notice(row.status+(row.error?' · '+row.error:''),row.status==='failed');
    showInvocations();
    if(['completed','failed','cancelled','interrupted'].includes(row.status)){
      $('cancel').disabled=true;$('run').disabled=false;
      const output=row.result?.node_outputs?.output||row.outputs||{};
      $('answer').textContent=output.answer||'';
      $('sql').textContent=output.prediction?.sql||'';
      renderTable(output.observation);
      $('run-error').hidden=!row.error;$('run-error').textContent=row.error||'';
      if(row.definition.kind==='offline'){await data();$('answer').textContent=fmt(row.outputs||row.error);offerReturn(row.status)}
      return;
    }
    polling=setTimeout(watch,700);
  }catch(e){if(runId!==watching)return;notice('Mất kết nối, đang nối lại: '+e.message,true);polling=setTimeout(watch,2000)}
}
function renderTable(observation){$('table').replaceChildren();if(!observation)return;const message=document.createElement('p');message.textContent=observation.status+' · '+(observation.row_count_returned??observation.preview?.length??0)+' dòng hiển thị'+(observation.truncated?' · Kết quả đã giới hạn':'');$('table').append(message);const table=document.createElement('table');for(const [index,row] of [observation.columns||[],...(observation.preview||[])].entries()){const tr=document.createElement('tr');for(const value of row){const td=document.createElement(index===0?'th':'td');td.textContent=value===null?'NULL':String(value);tr.append(td)}table.append(tr)}$('table').append(table)}

// Events carry scope "<node>/<invocation>[/<node>/<invocation>…]"; the node ids
// sit at the even positions and identify which subgraph the event belongs to.
function scopeKey(){return stack.length?scopePath().join('/'):''}
function scopeOf(event){return (event.scope||'').split('/').filter((_,i)=>i%2===0).join('/')}
function scopePath(){return stack.map((parent,index)=>parent.nodes.find(n=>n.config.body===(stack[index+1]||current)).id)}
function invocationEvents(...types){const prefix=scopeKey();return records.filter(e=>e.node_id===selected&&types.includes(e.type)&&scopeOf(e)===prefix)}
function showInvocations(){const previous=$('invocation').value;const matches=invocationEvents('node_completed','node_failed');$('invocation').replaceChildren(...matches.map(e=>new Option((e.scope||'root')+' / '+e.invocation_id,e.invocation_id)));if(matches.some(e=>e.invocation_id===previous))$('invocation').value=previous;else if(matches.length)$('invocation').value=matches[matches.length-1].invocation_id;const display=()=>{const event=matches.find(e=>e.invocation_id===$('invocation').value);const started=records.find(e=>e.invocation_id===event?.invocation_id&&e.type==='node_started');$('node-output').textContent=event?fmt({...event,inputs:started?.inputs}):'Node chưa có dữ liệu chạy.';};$('invocation').onchange=display;display();}

async function history(){const rows=await api('/studio/runs');$('run-list').replaceChildren(...rows.map(row=>card(row.workflow_id+' · '+row.status,row.created_at+' · rev '+row.revision,()=>{open(row.definition,true);runId=row.id;cursor=0;records=[];statuses={};$('events').replaceChildren();watch()})));}

// --- Datasets: split into "available" (repo, needs offline prep) vs "imported" (ready), no run-button hijack ---
function prepareCard(dataset){
  const box=document.createElement('div');box.className='card';
  const title=document.createElement('b'),small=document.createElement('small');
  title.textContent=dataset.label||dataset.id;
  small.textContent='Nguồn có sẵn · Cần chuẩn bị offline. P1 chỉ cần Schema only.';
  const chip=document.createElement('span');chip.className='chip index';chip.textContent='Cần offline';
  const actions=document.createElement('div');actions.className='card-actions';
  const schemaOnly=document.createElement('button');schemaOnly.textContent='Schema only';
  schemaOnly.onclick=action(()=>prepareSelectedDatasetById(dataset.id,false));
  const indexed=document.createElement('button');indexed.className='primary';indexed.textContent='Có index';
  indexed.onclick=action(()=>prepareSelectedDatasetById(dataset.id,true));
  actions.append(schemaOnly,indexed);box.append(title,small,chip,actions);return box;
}
// Every dataset stays selectable. Whether it can run *this* pipeline is
// explained next to the question, with the preparation buttons right there.
function selectedDataset(){return datasets.find(c=>c.id===$('dataset').value)}
function datasetProblem(c){
  if(!workflow||workflow.kind!=='online')return null;
  if(!c)return 'Chọn dữ liệu trước khi chạy.';
  if(c.ready===false)return 'Dữ liệu "'+(c.label||c.id)+'" chưa được chuẩn bị. Bấm "Chuẩn bị" ở panel bên phải trước khi chạy.';
  if(workflow.requires_index&&!c.indexed)return 'Pipeline "'+(workflow.name||workflow.id)+'" cần index, nhưng "'+(c.label||c.id)+'" chỉ có schema.';
  return null;
}
function renderDatasetSelect(){
  const previous=$('dataset').value,select=$('dataset');
  if(!datasets.length){select.replaceChildren(new Option('Chưa có dữ liệu — mở Dữ liệu & Offline',''));updateDatasetStatus();return}
  const ready=datasets.filter(c=>c.ready!==false),raw=datasets.filter(c=>c.ready===false);
  const group=(label,rows)=>{const g=document.createElement('optgroup');g.label=label;g.append(...rows.map(c=>new Option((c.label||c.id)+(c.ready===false?'':c.indexed?' · có index':' · schema only'),c.id)));return g};
  select.replaceChildren(...[ready.length&&group('Đã import',ready),raw.length&&group('Có sẵn — cần chuẩn bị',raw)].filter(Boolean));
  const keep=datasets.find(c=>c.id===previous);
  // Prefer a dataset this pipeline can actually run on.
  const pick=keep&&!datasetProblem(keep)?keep:(ready.find(c=>!datasetProblem(c))||keep||ready[0]||raw[0]);
  select.value=pick.id;updateDatasetStatus();
}
function updateDatasetStatus(){
  const box=$('dataset-status'),actions=$('dataset-prepare-actions'),c=selectedDataset();
  if(!workflow||workflow.kind!=='online'){box.hidden=true;return}
  const problem=datasetProblem(c);box.hidden=false;box.classList.toggle('ok',!problem);actions.replaceChildren();
  if(!problem){$('dataset-status-text').textContent='✓ "'+(c.label||c.id)+'" sẵn sàng cho pipeline này ('+(c.indexed?'có index':'schema only')+').';return}
  $('dataset-status-text').textContent=problem;
  const button=(text,primary,fn)=>{const b=el('button',primary?'primary':null,text);b.onclick=action(fn);actions.append(b)};
  if(c&&c.ready===false){
    if(!workflow.requires_index)button('Chuẩn bị · Schema only',false,()=>prepareSelectedDatasetById(c.id,false,true));
    button('Chuẩn bị · Có index',true,()=>prepareSelectedDatasetById(c.id,true,true));
    if(workflow.requires_index)$('dataset-status-text').textContent+=' Pipeline này cần index.';
  }else if(c){
    const indexed=datasets.find(d=>d.ready!==false&&d.indexed);
    if(indexed)button('Dùng "'+(indexed.label||indexed.id)+'"',true,()=>{$('dataset').value=indexed.id;updateDatasetStatus()});
    const basic=templates.find(t=>!t.requires_index);
    if(basic)button('Chuyển sang '+(basic.name||basic.id),!indexed,async()=>{const id=c.id;await openPipeline(basic);$('dataset').value=id;updateDatasetStatus()});
  }else button('Mở Dữ liệu & Offline',true,async()=>{page('datasets');await data()});
}
$('dataset').onchange=()=>{const c=selectedDataset();if(c?.question&&!$('question').value.trim())$('question').value=c.question;updateDatasetStatus()};

// After an offline preparation started from a pipeline, offer the way back.
let returnTo=null;
function offerReturn(status){
  const button=$('return-pipeline');
  if(!returnTo||status!=='completed'){button.hidden=true;return}
  const template=templates.find(t=>t.id===returnTo.pipelineId),target=datasets.find(c=>c.id===returnTo.datasetId);
  if(!template||!target){button.hidden=true;return}
  button.textContent='↩ Quay lại '+(template.name||template.id)+' với "'+target.id+'"';button.hidden=false;
  button.onclick=action(async()=>{const id=target.id;returnTo=null;button.hidden=true;await openPipeline(template);$('dataset').value=id;updateDatasetStatus()});
}

async function data(){datasets=await api('/studio/datasets');
  renderDatasetSelect();
  const status=await api('/studio/datasets/status');
  const chip=c=>c.indexed?{text:'Có index',index:false}:{text:'Sẵn sàng',index:false};
  $('dataset-available').replaceChildren(...datasets.filter(c=>c.ready===false).map(prepareCard));
  $('dataset-imported').replaceChildren(
    ...datasets.filter(c=>c.ready!==false).map(c=>card(c.label||c.id,c.indexed?'Có index · Dùng để hỏi':'Schema only · Dùng để hỏi',()=>{$('dataset').value=c.id;$('question').value=c.question;page('pipelines')},chip(c))),
    ...status.filter(c=>c.status!=='ready').map(c=>card(c.id+' · '+c.status,c.error||c.current_stage||'Đang chờ',async()=>{page('history');await history()},{text:c.status,index:false})));
}
async function prepareSelectedDatasetById(datasetId,indexed,comeBack=false){
  submitting=true;notice('Đang chuẩn bị dữ liệu nguồn…');
  try{
    const source=datasets.find(c=>c.id===datasetId);
    const origin=workflow?.kind==='online'?workflow.id:null;
    const definition=await api('/studio/datasets/prepare-repository',json('POST',{dataset_id:datasetId,indexed,question:$('question').value}));
    returnTo=comeBack&&origin&&source?.import_name?{pipelineId:origin,datasetId:source.import_name}:null;
    open(definition);$('return-pipeline').hidden=true;
    notice('Đã mở pipeline chuẩn bị dữ liệu ('+(indexed?'có index':'schema only')+'). Bấm ▶ Chạy toàn pipeline.');
  }finally{submitting=false}
}

// --- API key: sent with each run / node test only; never saved server-side ---
const KEY_STORE='sqlstudio.apiKey';
function apiKey(){return $('api-key').value.trim()||null}
function apiKeyHint(){
  const provider=$('run-provider').value||settings.api?.provider,env=settings.api?.providers?.[provider]?.api_key_env;
  $('api-key-provider').textContent=provider?'('+provider+')':'';
  $('api-key-hint').textContent=apiKey()
    ?'Key chỉ gửi kèm lần chạy và lần debug node; server che key trong nhật ký, không lưu vào workflow hay lịch sử. Key phải thuộc provider '+provider+'.'
    :'Để trống: server dùng '+(env||'biến môi trường')+' trong src/branch_sql_MVP/.env.';
}
function rememberKey(){try{if($('api-key-remember').checked&&apiKey())sessionStorage.setItem(KEY_STORE,apiKey());else sessionStorage.removeItem(KEY_STORE)}catch(e){}}
$('api-key').addEventListener('input',()=>{rememberKey();apiKeyHint()});
$('api-key-remember').addEventListener('change',rememberKey);
try{const stored=sessionStorage.getItem(KEY_STORE);if(stored){$('api-key').value=stored;$('api-key-remember').checked=true}}catch(e){}

function syncModelControls(){$('basic-provider').value=settings.api.provider;$('basic-model').value=settings.api.model;$('basic-device').value=settings.embedding.device;$('run-provider').value=settings.api.provider;$('run-model').value=settings.api.model;apiKeyHint()}
function settingsForm(){syncModelControls();const root=$('setting-groups');root.replaceChildren();for(const [key,value]of Object.entries(settings)){const details=document.createElement('details'),summary=document.createElement('summary'),textarea=document.createElement('textarea');summary.textContent=key;textarea.dataset.setting=key;textarea.value=fmt(value);textarea.style.minHeight='240px';details.append(summary,textarea);root.append(details)}}
document.querySelectorAll('[data-page]').forEach(button=>button.onclick=action(async()=>{page(button.dataset.page);if(button.dataset.page==='history')await history();if(button.dataset.page==='pipelines')await catalog();if(button.dataset.page==='datasets')await data()}));
for(const id of ['node-label','config','system-prompt','user-prompt','llm-provider','llm-model','llm-temperature','llm-max-tokens','llm-response-format'])$(id).addEventListener('input',()=>{nodeDirty=true});
$('run').onclick=action(run);$('back').onclick=action(async()=>{if(!closeNode())return;page('pipelines');await catalog()});
$('pipeline-select').onchange=action(async()=>{const next=templates.find(t=>t.id===$('pipeline-select').value);if(next)await openPipeline(next)});
$('revert').onclick=action(async()=>{
  const template=templates.find(t=>t.id===workflow.id);
  if(!template)throw Error('Pipeline này không có bản mẫu để khôi phục.');
  if(!confirm('Khôi phục '+(template.name||template.id)+' về cấu hình mặc định? Mọi prompt đã sửa sẽ mất.'))return;
  const result=await api('/studio/workflows/'+encodeURIComponent(workflow.id),json('PUT',{...structuredClone(template),revision:workflow.revision}));
  open({...structuredClone(template),revision:result.revision},true);notice('Đã khôi phục cấu hình mặc định.');
});
$('preview').onclick=action(async()=>{if(!apply())return;const node=graph().nodes.find(n=>n.id===selected);inspectorTab('output');$('node-output').textContent=fmt(await api('/studio/llm/preview',json('POST',{config:node.config,inputs:JSON.parse($('test-input').value)})))});
$('test').onclick=action(async()=>{if(!apply())return;const scope=scopePath();await ensureSaved();inspectorTab('output');$('node-output').textContent=fmt(await api(`/studio/workflows/${workflow.id}/nodes/${selected}/test`,json('POST',{revision:workflow.revision,scope,run_id:runId,api_key:apiKey(),inputs:JSON.parse($('test-input').value)})))});
$('cancel').onclick=action(async()=>{await api('/studio/runs/'+runId+'/cancel',json('POST',{}));notice('Đã yêu cầu dừng tại ranh giới node')});$('refresh-history').onclick=action(history);
$('settings-form').onsubmit=action(async event=>{event.preventDefault();const patch={};document.querySelectorAll('[data-setting]').forEach(el=>patch[el.dataset.setting]=JSON.parse(el.value));settings=await api('/settings',json('PATCH',patch));settingsForm();notice('Đã lưu Settings')});
$('basic-settings').onsubmit=action(async event=>{event.preventDefault();settings=await api('/settings',json('PATCH',{api:{provider:$('basic-provider').value.trim(),model:$('basic-model').value.trim()},embedding:{device:$('basic-device').value}}));settingsForm();notice('Đã lưu model và thiết bị mặc định');});
$('upload').onsubmit=action(async event=>{event.preventDefault();notice('Đang import…');const response=await fetch('/studio/datasets/upload',{method:'POST',body:new FormData(event.currentTarget)});if(!response.ok)throw Error(await response.text());const definition=await response.json();open(definition);notice('Đã upload. Kiểm tra node offline rồi bấm Chạy.');});
(async()=>{try{[templates,library,settings]=await Promise.all([api('/studio/workflow-templates'),api('/studio/node-types'),api('/settings')]);const providers=Object.keys(settings.api.providers);$('pipeline-select').replaceChildren(...templates.map(t=>new Option(t.name||t.id,t.id)));$('llm-provider').append(...providers.map(p=>new Option(p,p)));$('run-provider').replaceChildren(...providers.map(p=>new Option(p,p)));$('basic-provider').replaceChildren(...providers.map(p=>new Option(p,p)));syncModelControls();await catalog();await data();settingsForm()}catch(e){notice(e.message,true)}})();
// Provider and model are two independent settings: always send both.
const saveRunModel=action(async()=>{const provider=$('run-provider').value,model=$('run-model').value.trim();if(!model)return;settings=await api('/settings',json('PATCH',{api:{provider,model}}));syncModelControls();notice('Model mặc định: '+provider+' / '+model)});
$('run-provider').onchange=saveRunModel;$('run-model').onchange=saveRunModel;

(async()=>{try{const schema=await api('/openapi.json');const operations=[];for(const [path,methods] of Object.entries(schema.paths)){if(path.startsWith('/studio/')||path==='/settings')continue;for(const method of ['get','post'])if(methods[method])operations.push({path,method,schema:methods[method]})}$('tool-endpoint').replaceChildren(...operations.map((op,index)=>new Option(op.method.toUpperCase()+' '+op.path,index)));$('tool-endpoint').onchange=()=>{const op=operations[$('tool-endpoint').value];if(!op)return;$('tool-path').value=op.path;$('tool-schema').textContent=fmt(op.schema)};$('tool-endpoint').onchange();$('tool-run').onclick=action(async()=>{const op=operations[$('tool-endpoint').value];const path=$('tool-path').value;if(!path.startsWith('/')||path.startsWith('//'))throw Error('Chỉ gọi API local');$('tool-result').textContent=fmt(await api(path,op.method==='get'?undefined:json('POST',JSON.parse($('tool-body').value))))})}catch(e){notice(e.message,true)}})();

function inspectorTab(name){document.querySelectorAll('[data-inspector-panel]').forEach(el=>el.hidden=el.dataset.inspectorPanel!==name);document.querySelectorAll('[data-inspector-tab]').forEach(el=>el.classList.toggle('primary',el.dataset.inspectorTab===name))}
document.querySelectorAll('[data-inspector-tab]').forEach(button=>button.onclick=()=>inspectorTab(button.dataset.inspectorTab));
inspectorTab('config');
function resultTab(name){document.querySelectorAll('[data-result-panel]').forEach(el=>el.hidden=el.dataset.resultPanel!==name);document.querySelectorAll('[data-result-tab]').forEach(el=>el.classList.toggle('primary',el.dataset.resultTab===name))}
document.querySelectorAll('[data-result-tab]').forEach(button=>button.onclick=()=>resultTab(button.dataset.resultTab));
resultTab('answer');

$('use-run-input').onclick=action(()=>{const id=$('invocation').value;const event=records.find(e=>e.invocation_id===id&&e.type==='node_started');if(!event)throw Error('Chạy toàn pipeline trước hoặc nhập input debug thủ công.');$('test-input').value=fmt(event.inputs);notice('Đã lấy input thật của invocation đã chọn');});
