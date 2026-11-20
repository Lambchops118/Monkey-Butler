'use strict';
const $ = id => document.getElementById(id);
const svg = $('graph'), viewport = $('viewport');
const ns = 'http://www.w3.org/2000/svg';
let nodes = [], edges = [], selected = null, zoom = 1, pan = {x: 0, y: 0}, drag = null, frame = 0;
const positions = new Map();
function element(tag, attributes = {}, value = '') {
  const e = document.createElementNS(ns, tag);
  for (const [key, val] of Object.entries(attributes)) e.setAttribute(key, val);
  e.textContent = value;
  return e;
}
function transform() { viewport.setAttribute('transform', `translate(${pan.x},${pan.y}) scale(${zoom})`); }
function fit() {
  if (!nodes.length) return;
  const xs = nodes.map(n => n.x), ys = nodes.map(n => n.y);
  const x = Math.min(...xs)-90, y = Math.min(...ys)-50;
  const w = Math.max(...xs)-x+150, h = Math.max(...ys)-y+70;
  zoom = Math.min(1.6, svg.clientWidth / w, svg.clientHeight / h);
  pan = {x: (svg.clientWidth-w*zoom)/2-x*zoom, y: (svg.clientHeight-h*zoom)/2-y*zoom};
  transform();
}
function paint() {
  for (const n of nodes) { n.el.setAttribute('transform', `translate(${n.x},${n.y})`); positions.set(n.id, {x:n.x,y:n.y}); }
  for (const e of edges) {
    const a = e.a, b = e.b;
    for (const [key, value] of Object.entries({x1:a.x,y1:a.y,x2:b.x,y2:b.y})) e.line.setAttribute(key,value);
    e.label.setAttribute('x',(a.x+b.x)/2); e.label.setAttribute('y',(a.y+b.y)/2-5);
  }
}
function layout() {
  let step = 0;
  function tick() {
    for (const n of nodes) { n.fx = -n.x*.01; n.fy = -n.y*.01; }
    for (let i=0;i<nodes.length;i++) for (let j=i+1;j<nodes.length;j++) {
      const a=nodes[i],b=nodes[j],dx=a.x-b.x || .1,dy=a.y-b.y || .1;
      const squared=dx*dx+dy*dy+100, force=200/squared;
      a.fx+=dx*force; a.fy+=dy*force; b.fx-=dx*force; b.fy-=dy*force;
    }
    for (const e of edges) {
      const dx=e.b.x-e.a.x,dy=e.b.y-e.a.y,d=Math.hypot(dx,dy)||1,f=(d-140)*.008;
      e.a.fx+=dx/d*f; e.a.fy+=dy/d*f; e.b.fx-=dx/d*f; e.b.fy-=dy/d*f;
    }
    for (const n of nodes) if (!drag || drag.node!==n) {
      n.x+=Math.max(-8,Math.min(8,n.fx)); n.y+=Math.max(-8,Math.min(8,n.fy));
    }
    paint();
    if (++step < 160) frame=requestAnimationFrame(tick);
    else fit();
  }
  frame=requestAnimationFrame(tick);
}
function detailLabel(title, value, pre=false) {
  const label=document.createElement('div'); label.className='detail-label'; label.textContent=title;
  const body=document.createElement(pre?'pre':'div'); body.textContent=value;
  $('detail').append(label,body);
}
function select(id) {
  selected=id;
  const n=nodes.find(n=>n.id===id);
  $('detail').replaceChildren();
  if (n) {
    detailLabel('Memory',n.content);
    detailLabel('Status',n.archived?'Archived':'Active');
    detailLabel('Updated',new Date(n.updated_at*1000).toLocaleString());
    detailLabel('Embedding',n.embedded?'Stored':'Not stored');
    detailLabel('ID',n.id);
    let evidence=n.source;
    try { evidence=JSON.stringify(JSON.parse(evidence),null,2); } catch (_) { /* Plain evidence text is valid. */ }
    detailLabel('Supporting evidence',evidence,true);
    const connected=edges.filter(e=>e.a.id===id||e.b.id===id);
    detailLabel('Connections in this view',connected.length ? '' : 'No stored edges in this view.');
    for (const e of connected) {
      const other=e.a.id===id?e.b:e.a, button=document.createElement('button');
      button.className='relation'; button.textContent=`${e.a.id===id?'→':'←'} ${e.relation}: ${other.content.slice(0,70)}`;
      button.onclick=()=>select(other.id); $('detail').append(button);
    }
  } else $('detail').textContent='Select a node to see its full text, evidence, and relationships.';
  filter();
}
function filter() {
  const query=$('search').value.toLowerCase().trim();
  $('list').replaceChildren();
  let count=0;
  for (const n of nodes) {
    const match=!query||n.content.toLowerCase().includes(query)||n.id.includes(query);
    n.el.classList.toggle('dim',!match);
    n.el.classList.toggle('selected',n.id===selected);
    if (match) {
      count++;
      const button=document.createElement('button');button.className='entry'+(n.id===selected?' selected':'');
      button.textContent=(n.archived?'[Archived] ':'')+n.content.slice(0,160);
      button.onclick=()=>select(n.id); $('list').append(button);
    }
  }
  for (const e of edges) e.el.classList.toggle('dim',query && !e.a.content.toLowerCase().includes(query) && !e.b.content.toLowerCase().includes(query));
  $('list-heading').textContent=`Memories · ${count} in view`;
}
function render(data) {
  cancelAnimationFrame(frame);
  $('nodes').replaceChildren(); $('edges').replaceChildren();
  nodes=(data.nodes||[]).map((n,i,all)=>({...n,...(positions.get(n.id)||{
    x:Math.cos(i*2.39996)*Math.sqrt(i+1)*35,y:Math.sin(i*2.39996)*Math.sqrt(i+1)*35})}));
  const byId=new Map(nodes.map(n=>[n.id,n]));
  edges=(data.edges||[]).map(e=>({...e,a:byId.get(e.source_id),b:byId.get(e.target_id)})).filter(e=>e.a&&e.b);
  for (const e of edges) {
    e.el=element('g',{class:'edge'});e.line=element('line');e.label=element('text',{'text-anchor':'middle'},e.relation);
    e.el.append(e.line,e.label);$('edges').append(e.el);
  }
  for (const n of nodes) {
    n.el=element('g',{class:'node'+(n.archived?' archived':''),tabindex:0,role:'button','aria-label':n.content});
    n.el.append(element('circle',{r:8}),element('text',{x:13,y:4},n.content.slice(0,45)+(n.content.length>45?'…':'')),element('title',{},n.content));
    n.el.addEventListener('pointerdown',event=>beginDrag(event,n));
    n.el.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select(n.id);}});
    $('nodes').append(n.el);
  }
  const validSelection=nodes.some(n=>n.id===selected)?selected:null;
  select(validSelection);paint();fit();
  if(nodes.length) layout();
  $('empty').hidden=!!nodes.length;
  $('empty').textContent=data.ok?'No memories stored for this filter. LTMS may still be processing, or may not have started.':data.error;
}
async function load() {
  $('refresh').disabled=true;$('status').textContent='Reading database…';
  try {
    const response=await fetch(`/api/ltms-graph?limit=${$('limit').value}&archived=${$('archived').checked?1:0}`,{cache:'no-store'});
    if(!response.ok) throw new Error(`HTTP ${response.status}`);
    const data=await response.json();render(data);
    const c=data.coverage;
    $('status').textContent=data.ok?`${c.shown_nodes} / ${c.total_nodes} nodes · ${c.shown_edges} / ${c.total_edges} edges · ${c.omitted_nodes} nodes and ${c.omitted_edges} edges omitted · Refreshed ${new Date().toLocaleTimeString()}`:data.error;
  } catch(error) {render({ok:false,error:'Could not read graph. Check the dashboard connection.'});$('status').textContent=`Graph unavailable: ${error.message}`;}
  finally {$('refresh').disabled=false;}
}
function beginDrag(event,node=null) {
  if(event.button!==0)return;event.preventDefault();event.stopPropagation();
  cancelAnimationFrame(frame);
  drag={node,x:event.clientX,y:event.clientY,moved:false};svg.setPointerCapture(event.pointerId);
}
svg.addEventListener('pointerdown',event=>beginDrag(event));
svg.addEventListener('pointermove',event=>{
  if(!drag)return;
  const dx=event.clientX-drag.x,dy=event.clientY-drag.y;
  if(Math.abs(dx)+Math.abs(dy)>2)drag.moved=true;
  if(drag.node){drag.node.x+=dx/zoom;drag.node.y+=dy/zoom;paint();}
  else {pan.x+=dx;pan.y+=dy;transform();}
  drag.x=event.clientX;drag.y=event.clientY;
});
svg.addEventListener('pointerup',event=>{if(drag?.node&&!drag.moved)select(drag.node.id);drag=null;if(svg.hasPointerCapture(event.pointerId))svg.releasePointerCapture(event.pointerId);});
svg.addEventListener('pointercancel',()=>{drag=null;});
svg.addEventListener('wheel',event=>{
  event.preventDefault();const rect=svg.getBoundingClientRect(),x=event.clientX-rect.left,y=event.clientY-rect.top;
  const next=Math.max(.1,Math.min(5,zoom*Math.exp(-event.deltaY*.001)));
  pan={x:x-(x-pan.x)*next/zoom,y:y-(y-pan.y)*next/zoom};zoom=next;transform();
},{passive:false});
$('refresh').onclick=load;$('archived').onchange=load;$('limit').onchange=load;
$('fit').onclick=fit;$('search').oninput=filter;
window.addEventListener('resize',fit);
load();
