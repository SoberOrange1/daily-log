#!/usr/bin/env python3
"""
render_dashboard.py —— 读 history.json,生成【单文件、零外部依赖】dashboard.html。

重要:Quick 的 session-tab 预览会拦截外部请求(CDN / Google Fonts 返回 403),
所以本 dashboard 不引任何外部资源 —— 全部内联 CSS + 系统字体,DATA 内联。

  • 编辑/技术感暗色主题(系统衬线做标题,系统无衬线做正文)。
  • 三层有向图:为什么(触发) → 动作 → 影响/TODO,SVG 连线成树状。
  • hover 任一节点 → 高亮它的连线 + 相邻(含下游)节点,其余淡出。
  • 为什么/影响 各带可折叠「依据」(源自对话原文);动作带可折叠「详情」(commit/文件)。
  • 里程碑(🏁)标记目标达成;TODO 被后续动作解决 → 虚线连回并标 ✓。
  • 时间连续不分页;右侧固定 goals sidebar(每项目独立时间轴 + 点击聚焦)。

用法:  python render_dashboard.py <history.json> <dashboard.html> [dashboard_days=60]
"""
import sys, json, os
from datetime import date, timedelta

HTML = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Daily Log</title>
<style>
  :root{--bg:#0a0c10;--ink:#e9e4da;--dim:#8a909b;--edge:#222b38;--accent:#e0a256;
    --font:system-ui,-apple-system,"Segoe UI",Roboto,"PingFang SC","Microsoft YaHei",sans-serif;
    --serif:Georgia,"Songti SC","STSong",serif;
    --mono:ui-monospace,"Cascadia Mono",Consolas,"Courier New",monospace}
  *{box-sizing:border-box}
  html,body{margin:0;background:var(--bg);color:var(--ink)}
  body{font-family:var(--font);font-size:15px;line-height:1.5;
    background:radial-gradient(1100px 560px at 12% -12%,#16202e66,transparent 60%),
               radial-gradient(820px 460px at 102% -4%,#1e18225e,transparent 55%),var(--bg);
    background-attachment:fixed}
  .serif{font-family:var(--serif)}
  .mono{font-family:var(--mono)}
  .dim{color:var(--dim)}
  a{color:inherit;text-decoration:none}
  ::-webkit-scrollbar{width:9px;height:9px}::-webkit-scrollbar-thumb{background:#26334a;border-radius:9px}

  .app{display:flex;min-height:100vh}
  .side{flex:none;padding:20px;position:sticky;top:0;height:100vh;overflow:auto}
  .side-l{width:200px;border-right:1px solid #141c28}
  .side-r{width:280px;border-left:1px solid #141c28}
  .main{flex:1;min-width:0;padding:28px}
  #wrap{position:relative}
  #wires{position:absolute;inset:0;pointer-events:none;z-index:1;overflow:visible}
  #content{position:relative;z-index:2}
  #grain{position:fixed;inset:0;pointer-events:none;z-index:50;opacity:.035;mix-blend-mode:overlay;
    background:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")}

  .title{font-family:var(--serif);font-size:26px;font-weight:600;letter-spacing:-.01em}
  .col-h{font-family:var(--mono);font-size:10.5px;letter-spacing:.18em;text-transform:uppercase;color:var(--dim);margin-bottom:10px}
  .navlink{display:block;padding:3px 10px;border-radius:8px;color:var(--dim);font-size:13px;cursor:pointer}
  .navlink:hover{background:#141c28;color:var(--ink)}
  .navlink.on{color:var(--accent);background:#141c28}

  .datehead{position:sticky;top:0;z-index:3;padding:8px 0;margin-bottom:16px;border-bottom:1px solid #16202f;
    font-family:var(--mono);font-size:12px;letter-spacing:.2em;color:var(--dim);
    background:linear-gradient(180deg,var(--bg),rgba(10,12,16,.6))}
  .entry{margin-bottom:28px}
  .entry-head{display:flex;align-items:center;gap:8px;margin-bottom:12px}
  .proj{font-family:var(--serif);font-weight:600;font-size:18px}
  .cols{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:32px;align-items:start}
  .cols>div{min-width:0}
  .stack>*+*{margin-top:12px}

  .node{background:linear-gradient(180deg,#131a25,#0f141c);border:1px solid var(--edge);border-radius:13px;
    padding:11px 13px;position:relative;transition:opacity .16s,transform .12s,box-shadow .16s;
    overflow-wrap:anywhere;word-break:break-word}
  .node:hover{transform:translateY(-1px);box-shadow:0 8px 26px rgba(0,0,0,.5)}
  .noderow{margin-top:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap}
  .pill{font-size:11px;padding:1px 8px;border-radius:9999px;white-space:nowrap;display:inline-block}
  .goaltag{max-width:100%;min-width:0;overflow:hidden;text-overflow:ellipsis;flex:0 1 auto}
  .detbtn{font-family:var(--mono);font-size:10.5px;color:var(--dim);cursor:pointer;user-select:none}
  .detbtn:hover{color:var(--accent)}
  .det{margin-top:6px}.det.hidden{display:none}
  .det-box{margin-top:6px;padding-top:6px;border-top:1px solid var(--edge);font-size:11px;color:var(--dim);overflow-wrap:anywhere;word-break:break-all}
  .quote{border-left:2px solid var(--accent);padding:2px 0 2px 9px;font-style:italic;color:#b9bcc4;font-size:13.5px}
  .small{font-size:11px;color:var(--dim)}

  .gitem{cursor:pointer;border-radius:10px;padding:8px 9px}.gitem:hover{background:#141c28}
  .gitem.on{box-shadow:inset 0 0 0 1px var(--accent)}
  .dot{width:9px;height:9px;border-radius:9px;display:inline-block;flex:none;margin-top:6px}
  .bar-track{position:relative;height:6px;flex:1;border-radius:6px;background:#141c28}
  .bar{position:absolute;height:6px;border-radius:6px}

  /* 响应式:小屏缩字号/间距/侧栏,给中间三层腾地方,避免挤压 */
  @media (max-width:1200px){
    body{font-size:14px}
    .cols{gap:20px} .main{padding:20px} .proj{font-size:17px}
    .side-l{width:172px} .side-r{width:224px}
  }
  @media (max-width:900px){
    body{font-size:13px}
    .cols{gap:12px} .main{padding:14px} .proj{font-size:15px}
    .node{padding:9px 10px;border-radius:11px}
    .quote{font-size:12.5px}
    .side{padding:12px} .side-l{width:150px} .side-r{width:192px}
  }
</style>
</head>
<body>
<div id="grain"></div>
<div class="app">
  <aside class="side side-l">
    <div class="title">Daily<span style="color:var(--accent)">.</span>Log</div>
    <div id="updated" class="mono dim" style="font-size:10px;margin:4px 0 20px"></div>
    <div id="projfilter" style="margin-bottom:20px"></div>
    <div class="col-h">跳转日期</div>
    <nav id="datenav"></nav>
  </aside>
  <main class="main">
    <div id="wrap"><svg id="wires"></svg><div id="content"></div></div>
  </main>
  <aside class="side side-r">
    <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:14px">
      <div class="serif" style="font-weight:600">目标线</div>
      <span id="clearfocus" class="detbtn hidden" onclick="setGoal(null)">清除聚焦</span>
    </div>
    <div id="goalsbar"></div>
  </aside>
</div>

<script>
const DATA = __DATA__;
const PALETTE = ["#e0a256","#5ec8c8","#e07a9b","#8a86e6","#6db1e6","#c9d06a","#e08a5e","#6ecf9e"];
const STATUS = {on_track:["正常推进","#5ec8c8"],at_risk:["有风险","#e0a256"],
  needs_decision:["需决策","#e07a9b"],insufficient_info:["信息不足","#8a909b"]};
const ITYPE = {todo:["TODO","#6db1e6"],risk:["风险","#e0a256"]};
const MILE="#e6b84a", DONE="#6ecf9e";

let projFilter=null, goalFocus=null, hoverSel=null;
let EDGES=[], ADJ={}, RESOLVED=new Set();

function esc(s){return (s==null?"":String(s)).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function base(f){return (f||"").split(/[\\\/]/).pop();}
function projects(){return [...new Set(Object.keys(DATA.entries))].sort();}
function shownProjects(){return projects().filter(p=>!projFilter||p===projFilter);}
function allDates(){const s=new Set();for(const p in DATA.entries)for(const d in DATA.entries[p])s.add(d);return [...s].sort().reverse();}
function goalColor(project,gid){
  if(!gid)return "#334155";
  const arr=Object.keys(DATA.goals[project]||{}).sort(); let i=arr.indexOf(gid);
  if(i<0){let h=0;for(const c of gid)h=(h*31+c.charCodeAt(0))>>>0;i=h;}
  return PALETTE[i%PALETTE.length];
}
function goalTitle(project,gid){const g=(DATA.goals[project]||{})[gid];return g?g.title:gid;}
function fold(label,inner){return `<span class="detbtn" onclick="tog(this)">${label} ▾</span><div class="det hidden">${inner}</div>`;}

function entryHTML(e){
  const key=`${e.project}__${e.date}`;
  const [slabel,scol]=STATUS[e.status]||["",""];
  const whyNodes=(e.why||[]).map(w=>
    `<div class="node" data-node="${key}:${w.id}" style="border-left:3px solid #6b7480">${esc(w.text)}
       ${w.evidence?fold("依据",`<div class="quote">${esc(w.evidence)}</div>`):""}</div>`).join("");
  const chNodes=(e.changes||[]).map(c=>{
    const col=goalColor(e.project,c.goal_id);
    const files=(c.files||[]).map(base).filter(Boolean).join(", ");
    const det=[c.commit?`<div class="mono">commit ${esc(c.commit)}</div>`:"", files?`<div>${esc(files)}</div>`:""].join("");
    return `<div class="node" data-node="${key}:${c.id}" data-goal="${e.project}::${c.goal_id||''}" style="border-left:3px solid ${col}">
      <div>${esc(c.summary)}</div>
      <div class="noderow">
        ${c.goal_id?`<span class="pill goaltag" title="${esc(goalTitle(e.project,c.goal_id))}" style="background:${col}1f;color:${col}">◆ ${esc(goalTitle(e.project,c.goal_id))}</span>`:""}
        ${det?`<span class="detbtn" onclick="tog(this)">详情 ▾</span>`:""}
      </div>
      ${det?`<div class="det hidden"><div class="det-box">${det}</div></div>`:""}
    </div>`;}).join("");
  const mileNodes=(e.milestones||[]).map(m=>
    `<div class="node" data-node="${key}:${m.id}" style="border-left:3px solid ${MILE};background:linear-gradient(180deg,#1c1a12,#12100b)">
      <span class="pill" style="background:${MILE}22;color:${MILE};margin-bottom:4px">🏁 里程碑</span>
      <div>${esc(m.text)}</div>
      ${m.goal_id?`<div class="small" style="margin-top:4px;color:${MILE}">达成目标:${esc(goalTitle(e.project,m.goal_id))}</div>`:""}
    </div>`).join("");
  const imNodes=(e.impact_todo||[]).map(t=>{
    const [tl,tc]=ITYPE[t.type]||["·","#94a3b8"];
    const done=RESOLVED.has(`${e.project}|${e.date}|${t.id}`);
    return `<div class="node" data-node="${key}:${t.id}" style="border-left:3px solid ${done?DONE:tc};${done?'opacity:.75':''}">
      <span class="pill" style="background:${(done?DONE:tc)}1f;color:${done?DONE:tc};margin-bottom:4px">${done?'✓ 已解决':tl}</span>
      <div style="${done?'text-decoration:line-through;text-decoration-color:'+DONE+'66':''}">${esc(t.text)}</div>
      ${t.evidence?fold("依据",`<div class="quote">${esc(t.evidence)}</div>`):""}</div>`;}).join("");
  const dim='<div class="dim">—</div>';
  return `<div class="entry">
    <div class="entry-head"><span class="proj">${esc(e.project)}</span>
      ${slabel?`<span class="pill" style="background:${scol}1f;color:${scol}">${slabel}</span>`:""}</div>
    <div class="cols">
      <div><div class="col-h">为什么(触发)</div><div class="stack">${whyNodes||dim}</div></div>
      <div><div class="col-h">动作</div><div class="stack">${chNodes||dim}</div></div>
      <div><div class="col-h">影响 &amp; TODO</div><div class="stack">${mileNodes}${imNodes||(mileNodes?'':dim)}</div></div>
    </div></div>`;
}
function graphView(){
  let html="";
  for(const d of allDates()){
    const es=shownProjects().map(p=>DATA.entries[p][d]).filter(Boolean);
    if(!es.length)continue;
    html+=`<section id="day-${d}" style="margin-bottom:44px"><div class="datehead">${d}</div>${es.map(entryHTML).join("")}</section>`;
  }
  return html||`<div class="dim">暂无数据</div>`;
}

// —— 边与邻接 ——
function buildEdges(){
  EDGES=[]; ADJ={}; RESOLVED=new Set();
  const add=(a,b,color,op,dash,goalKey)=>{EDGES.push({a,b,color,op,dash,goalKey});
    (ADJ[a]=ADJ[a]||new Set()).add(b);(ADJ[b]=ADJ[b]||new Set()).add(a);};
  for(const p of shownProjects()){
    for(const d in DATA.entries[p]){
      const e=DATA.entries[p][d], key=`${p}__${d}`;
      (e.changes||[]).forEach(c=>{const gk=`${p}::${c.goal_id||''}`;
        (c.from_why||[]).forEach(w=>add(`${key}:${w}`,`${key}:${c.id}`,"#4a5468",.5,false,gk));
        (c.resolves||[]).forEach(ref=>{const [rd,tid]=String(ref).split(":");
          RESOLVED.add(`${p}|${rd}|${tid}`);
          add(`${p}__${rd}:${tid}`,`${key}:${c.id}`,DONE,.7,true,gk);});});
      (e.impact_todo||[]).forEach(t=>{const [,tc]=ITYPE[t.type]||["","#94a3b8"];
        (t.caused_by||[]).forEach(cid=>{const ch=(e.changes||[]).find(x=>x.id===cid);
          add(`${key}:${cid}`,`${key}:${t.id}`,tc,.6,false,`${p}::${ch?ch.goal_id||'':''}`);});});
      (e.milestones||[]).forEach(m=>{const gk=`${p}::${m.goal_id||''}`;
        (m.caused_by||[]).forEach(cid=>add(`${key}:${cid}`,`${key}:${m.id}`,MILE,.7,false,gk));});
    }
  }
}
function center(sel,side){
  const el=document.querySelector(`[data-node="${sel}"]`); if(!el)return null;
  const c=document.getElementById("content").getBoundingClientRect(), r=el.getBoundingClientRect();
  return {x:(side==="r"?r.right:r.left)-c.left, y:r.top-c.top+r.height/2};
}
function computeResolved(){
  RESOLVED=new Set();
  for(const p in DATA.entries) for(const d in DATA.entries[p])
    (DATA.entries[p][d].changes||[]).forEach(c=>(c.resolves||[]).forEach(ref=>{
      const [rd,tid]=String(ref).split(":"); RESOLVED.add(`${p}|${rd}|${tid}`);}));
}
function drawWires(){
  const svg=document.getElementById("wires"), content=document.getElementById("content");
  svg.setAttribute("width",content.scrollWidth); svg.setAttribute("height",content.scrollHeight);
  let s="";
  EDGES.forEach((e,i)=>{
    if(e.dash){
      const a=center(e.a,"r"),b=center(e.b,"r"); if(!a||!b)return;
      const bend=Math.max(a.x,b.x)+46;
      s+=`<path data-i="${i}" d="M${a.x},${a.y} C${bend},${a.y} ${bend},${b.y} ${b.x},${b.y}" fill="none" stroke="${e.color}" stroke-width="1.5" stroke-dasharray="4 5"/>`;
    }else{
      const a=center(e.a,"r"),b=center(e.b,"l"); if(!a||!b)return;
      const dx=Math.max(34,(b.x-a.x)/2);
      s+=`<path data-i="${i}" d="M${a.x},${a.y} C${a.x+dx},${a.y} ${b.x-dx},${b.y} ${b.x},${b.y}" fill="none" stroke="${e.color}" stroke-width="1.6"/>`;}
  });
  svg.innerHTML=s; applyStyles();
}
function applyStyles(){
  const hot = hoverSel ? new Set([hoverSel, ...(ADJ[hoverSel]||[])]) : null;
  let gset=null;
  if(goalFocus){
    gset=new Set();
    document.querySelectorAll("[data-goal]").forEach(el=>{
      if(el.getAttribute("data-goal")===goalFocus) gset.add(el.getAttribute("data-node"));});
    [...gset].forEach(s=>(ADJ[s]||[]).forEach(n=>gset.add(n)));
  }
  document.querySelectorAll("[data-node]").forEach(el=>{
    const sel=el.getAttribute("data-node");
    let op=1;
    if(gset) op = gset.has(sel) ? 1 : .12;
    if(hot)  op = hot.has(sel) ? 1 : .12;
    el.style.opacity=op;
  });
  document.querySelectorAll("#wires path").forEach(pt=>{
    const e=EDGES[+pt.getAttribute("data-i")]; if(!e)return;
    let op=e.op, w=1.6;
    if(gset){const on=gset.has(e.a)&&gset.has(e.b); op=on?.9:.04; w=on?2.2:1.6;}
    if(hot){const on=(e.a===hoverSel||e.b===hoverSel); op=on?.95:.04; w=on?2.4:1.6;}
    pt.setAttribute("opacity",op); pt.setAttribute("stroke-width",w);
  });
}
function attachHover(){
  document.querySelectorAll("[data-node]").forEach(el=>{
    el.addEventListener("mouseenter",()=>{hoverSel=el.getAttribute("data-node");applyStyles();});
    el.addEventListener("mouseleave",()=>{hoverSel=null;applyStyles();});
  });
}

function goalsBar(){
  let html="";
  for(const p of shownProjects()){
    const goals=DATA.goals[p]||{}; const gids=Object.keys(goals); if(!gids.length)continue;
    const firsts=gids.map(g=>+new Date(goals[g].first_seen)), lasts=gids.map(g=>+new Date(goals[g].last_seen));
    const pmin=Math.min(...firsts), pmax=Math.max(...lasts), span=Math.max(1,(pmax-pmin)/864e5);
    let items="";
    for(const gid of gids){const g=goals[gid],col=goalColor(p,gid);
      const l=100*(+new Date(g.first_seen)-pmin)/864e5/span;
      const w=100*(+new Date(g.last_seen)-+new Date(g.first_seen))/864e5/span;
      const on=goalFocus===`${p}::${gid}`, done=g.status==="delivered";
      items+=`<div class="gitem ${on?'on':''}" onclick="setGoal('${p}::${gid}')" title="${esc(g.title)}">
        <div style="display:flex;align-items:flex-start;gap:8px;margin-bottom:6px">
          <span class="dot" style="background:${col}"></span>
          <span style="line-height:1.35">${done?'<span style="color:'+DONE+'">✓ </span>':''}${esc(g.title)}</span></div>
        <div style="display:flex;align-items:center;gap:8px">
          <div class="bar-track"><div class="bar" style="left:${l}%;width:${w}%;min-width:10px;background:${col};${done?'box-shadow:0 0 0 1.5px '+DONE:''}"></div></div>
          <span class="pill" style="background:${(done?DONE:col)}1f;color:${done?DONE:col}">${g.status}</span></div>
        <div class="mono small" style="margin-top:5px">${g.first_seen} → ${g.last_seen}</div>
      </div>`;}
    const axis=new Date(pmin).toISOString().slice(0,10)+" → "+new Date(pmax).toISOString().slice(0,10);
    html+=`<div style="margin-bottom:20px"><div class="col-h">${esc(p)}</div>
      <div class="mono small" style="margin-bottom:6px">轴 ${axis}</div>${items}</div>`;
  }
  return html||`<div class="dim small">尚未检测到目标</div>`;
}

function render(){
  document.getElementById("updated").textContent=(DATA.updated_at||"").slice(0,16).replace("T"," ");
  const chip=p=>`<div onclick="setProj('${p}')" class="navlink ${projFilter===p?'on':''}">${esc(p)}</div>`;
  document.getElementById("projfilter").innerHTML=
    `<div class="col-h">项目</div><div onclick="setProj(null)" class="navlink ${projFilter?'':'on'}">全部</div>`+projects().map(chip).join("");
  document.getElementById("datenav").innerHTML=allDates().map(d=>`<a class="navlink mono" href="#day-${d}">${d}</a>`).join("")||'<div class="dim small">无</div>';
  computeResolved();
  document.getElementById("content").innerHTML=graphView();
  document.getElementById("goalsbar").innerHTML=goalsBar();
  document.getElementById("clearfocus").classList.toggle("hidden",!goalFocus);
  buildEdges(); attachHover();
  requestAnimationFrame(drawWires);
}
function setProj(p){projFilter=p;goalFocus=null;hoverSel=null;render();}
function setGoal(g){goalFocus=(goalFocus===g)?null:g;hoverSel=null;render();}
function tog(btn){const d=btn.closest(".node").querySelector(".det");
  if(d){d.classList.toggle("hidden");requestAnimationFrame(drawWires);}}
window.addEventListener("resize",()=>requestAnimationFrame(drawWires));
render();
</script>
</body>
</html>
"""


def render_html(data: dict, window_days: int = 60) -> str:
    """把 history 数据渲染成单文件自包含 HTML(只内联最近 window_days 天)。会就地修改 data。"""
    all_dates = sorted({d for days in data.get("entries", {}).values() for d in days})
    if window_days and all_dates:
        cutoff = (date.fromisoformat(all_dates[-1]) - timedelta(days=window_days)).isoformat()
        for p in list(data["entries"]):
            data["entries"][p] = {d: v for d, v in data["entries"][p].items() if d >= cutoff}
            if not data["entries"][p]:
                del data["entries"][p]
    return HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))


def main():
    history_path, out_path = sys.argv[1], sys.argv[2]
    window_days = int(sys.argv[3]) if len(sys.argv) > 3 else 60
    data = json.load(open(history_path, encoding="utf-8"))
    html = render_html(data, window_days)
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    open(out_path, "w", encoding="utf-8").write(html)
    pd = sum(len(v) for v in data.get("entries", {}).values())
    print(f"[render] {out_path}  ({len(html)} bytes, window={window_days}d, {pd} project-days)")


if __name__ == "__main__":
    main()
