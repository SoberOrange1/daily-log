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
    display:flex;align-items:center;gap:10px;
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

  /* 每日速览:datehead 旁的折叠下拉(默认折叠) */
  .daysum-btn{font-family:var(--mono);font-size:10.5px;letter-spacing:.04em;color:var(--dim);
    cursor:pointer;user-select:none;padding:1px 9px;border:1px solid var(--edge);border-radius:9999px}
  .daysum-btn:hover{color:var(--accent);border-color:var(--accent)}
  .daysum{margin:-6px 0 18px;padding:12px 15px;background:linear-gradient(180deg,#141b27,#0f141c);
    border:1px solid var(--edge);border-left:3px solid var(--accent);border-radius:12px;
    font-size:14px;line-height:1.62;color:var(--ink);overflow-wrap:anywhere;letter-spacing:normal}
  .daysum.hidden{display:none}
  .ds-head{font-weight:600;color:var(--ink);margin-bottom:6px}
  .ds-proj{font-family:var(--mono);font-size:11px;letter-spacing:.04em;color:var(--accent);margin:8px 0 2px}
  .ds-pts{margin:0 0 4px;padding-left:18px}
  .ds-pts li{font-size:13px;line-height:1.5;color:#c7ccd6;margin:2px 0}
  /* 侧栏「周汇总」区 */
  .weekitem{display:block;padding:5px 10px;border-radius:8px;color:var(--dim);font-size:12px;
    font-family:var(--mono);cursor:pointer}
  .weekitem:hover{background:#141c28;color:var(--ink)}
  .weekitem.all{color:var(--accent)}
  /* 周汇总全屏页(点某周或「全部」进入,月历按整周选) */
  #weekpage{position:fixed;inset:0;z-index:100;display:none;background:var(--bg);overflow:auto}
  #weekpage.show{display:block}
  .wp-head{display:flex;align-items:center;justify-content:flex-start;gap:16px;padding:18px 28px;
    border-bottom:1px solid #16202f;position:sticky;top:0;background:var(--bg);z-index:2}
  .wp-x{cursor:pointer;color:var(--dim);font-family:var(--mono);font-size:12px}.wp-x:hover{color:var(--accent)}
  .wp-body{display:grid;grid-template-columns:320px 1fr;gap:32px;padding:26px 28px;align-items:start;max-width:1100px}
  .wp-report{min-width:0}
  .cal-nav{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
  .cal-nav b{font-family:var(--serif);font-size:16px}
  .cal-arrow{cursor:pointer;padding:2px 11px;border:1px solid var(--edge);border-radius:8px;color:var(--dim)}
  .cal-arrow:hover{color:var(--accent);border-color:var(--accent)}
  .cal-dow{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;margin-bottom:5px}
  .cal-dow span{text-align:center;font-family:var(--mono);font-size:10px;color:var(--dim)}
  .cal-wk{display:grid;grid-template-columns:repeat(7,1fr);gap:3px;border-radius:9px;padding:3px;
    margin-bottom:3px;border:1px solid transparent}
  .cal-wk.has{cursor:pointer;background:#121924;border-color:var(--edge)}
  .cal-wk.has:hover{border-color:var(--accent)}
  .cal-wk.on{border-color:var(--accent);background:#18202e}
  .cal-day{text-align:center;padding:6px 0;font-size:12px;color:#c7ccd6}
  .cal-day.out{color:#3a4150}
  .cal-wk.has .cal-day.rep{color:var(--accent);font-weight:600}
  .wp-rtitle{font-family:var(--serif);font-weight:600;font-size:18px;margin-bottom:12px}
  .wp-rtext{font-size:14.5px;line-height:1.75;color:var(--ink);overflow-wrap:anywhere}
  @media (max-width:820px){.wp-body{grid-template-columns:1fr;gap:20px}}

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
    <div id="weeklybox"></div>
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

<div id="weekpage">
  <div class="wp-head">
    <span class="wp-x" onclick="closeWeekPage()">‹ 返回</span>
    <div class="serif" style="font-weight:600;font-size:18px">周汇总</div>
  </div>
  <div class="wp-body">
    <div class="wp-cal">
      <div class="cal-nav">
        <span class="cal-arrow" onclick="calNav(-1)">‹</span>
        <b id="callabel"></b>
        <span class="cal-arrow" onclick="calNav(1)">›</span>
      </div>
      <div class="cal-dow"><span>一</span><span>二</span><span>三</span><span>四</span><span>五</span><span>六</span><span>日</span></div>
      <div id="calgrid"></div>
    </div>
    <div class="wp-report"><div class="wp-rtitle" id="wpTitle"></div><div class="wp-rtext" id="wpText"></div></div>
  </div>
</div>

<script>
const DATA = __DATA__;
const PALETTE = ["#e0a256","#5ec8c8","#e07a9b","#8a86e6","#6db1e6","#c9d06a","#e08a5e","#6ecf9e"];
const STATUS = {on_track:["正常推进","#5ec8c8"],at_risk:["有风险","#e0a256"],
  needs_decision:["需决策","#e07a9b"],insufficient_info:["信息不足","#8a909b"]};
const ITYPE = {todo:["TODO","#6db1e6"],risk:["风险","#e0a256"]};
const MILE="#e6b84a", DONE="#6ecf9e";

let projFilter=null, goalFocus=null, hoverSel=null;
let WEEKSEL=null, CALY=0, CALM=0;
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
function fmtSum(s){return esc(s).replace(/\n/g,"<br>");}
// 每日速览:datehead 旁的下拉(默认折叠)。结构 = headline(总主线)+ by_project(按项目的关键 action/TODO)。
function togDaysum(btn){const ds=btn.closest(".datehead").nextElementSibling;
  if(ds&&ds.classList.contains("daysum")){const h=ds.classList.toggle("hidden");
    btn.textContent=h?"速览 ▾":"速览 ▴";requestAnimationFrame(drawWires);}}
function hasDaysum(sd){return !!(sd&&(sd.headline||(sd.by_project&&sd.by_project.length)||sd.text));}
function daysumHTML(sd){
  if(sd.headline||sd.by_project){
    const h=sd.headline?`<div class="ds-head">${esc(sd.headline)}</div>`:"";
    const g=(sd.by_project||[]).map(x=>{
      const pts=(x.points||[]).map(p=>`<li>${esc(p)}</li>`).join("");
      return `<div class="ds-proj">${esc(x.project)}</div>`+(pts?`<ul class="ds-pts">${pts}</ul>`:"");
    }).join("");
    return h+g;
  }
  return fmtSum(sd.text||"");   // 兼容旧的纯字符串
}
function graphView(){
  const DS=(DATA.summaries&&DATA.summaries.daily)||{};
  let html="";
  for(const d of allDates()){
    const es=shownProjects().map(p=>DATA.entries[p][d]).filter(Boolean);
    if(!es.length)continue;
    const sd=DS[d], has=hasDaysum(sd);
    const head=`<div class="datehead"><span>${d}</span>`
      +(has?`<span class="daysum-btn" onclick="togDaysum(this)">速览 ▾</span>`:"")+`</div>`
      +(has?`<div class="daysum hidden">${daysumHTML(sd)}</div>`:"");
    html+=`<section id="day-${d}" style="margin-bottom:44px">${head}${es.map(entryHTML).join("")}</section>`;
  }
  return html||`<div class="dim">暂无数据</div>`;
}
// 侧栏「周汇总」:最近 3 周 + 「全部 →」入口(footprint 恒定,不随周数增长)
function weekMap(){return (DATA.summaries&&DATA.summaries.weekly)||{};}
function weekRange(k){const w=weekMap()[k]||{};
  return (w.range&&w.range.length===2)?`${w.range[0]} → ${w.range[1]}`:k;}
function weeklyNav(){
  const keys=Object.keys(weekMap()).sort().reverse();
  if(!keys.length)return "";
  const recent=keys.slice(0,3).map(k=>
    `<div class="weekitem" onclick="openWeekPage('${k}')">📄 ${weekRange(k).replace(/\d{4}-/g,"")}</div>`).join("");
  return `<div class="col-h" style="margin-top:24px">周汇总</div>${recent}`
    +`<div class="weekitem all" onclick="openWeekPage(null)">全部 (${keys.length}) →</div>`;
}
// 全屏页 + 月历(按整周点击)
function localISO(d){const y=d.getFullYear(),m=String(d.getMonth()+1).padStart(2,"0"),a=String(d.getDate()).padStart(2,"0");return `${y}-${m}-${a}`;}
function openWeekPage(key){
  const keys=Object.keys(weekMap()).sort().reverse(); if(!keys.length)return;
  WEEKSEL=key||keys[0];
  const d=new Date(WEEKSEL+"T00:00:00"); CALY=d.getFullYear(); CALM=d.getMonth();
  renderCal(); renderReport();
  document.getElementById("weekpage").classList.add("show");
}
function closeWeekPage(){document.getElementById("weekpage").classList.remove("show");}
function calNav(delta){CALM+=delta; if(CALM<0){CALM=11;CALY--;} if(CALM>11){CALM=0;CALY++;} renderCal();}
function selectWeek(k){WEEKSEL=k; renderCal(); renderReport();}
function renderReport(){
  document.getElementById("wpTitle").textContent="本周速览 · "+weekRange(WEEKSEL);
  document.getElementById("wpText").innerHTML=fmtSum((weekMap()[WEEKSEL]||{}).text||"");
}
function renderCal(){
  const W=weekMap();
  const first=new Date(CALY,CALM,1), dow=(first.getDay()+6)%7;
  const start=new Date(first); start.setDate(first.getDate()-dow);
  const lastOfMonth=new Date(CALY,CALM+1,0);
  let rows="", cur=new Date(start);
  while(cur<=lastOfMonth){
    const row=[]; for(let i=0;i<7;i++){const d=new Date(cur);d.setDate(cur.getDate()+i);row.push(d);}
    const r0=localISO(row[0]), r6=localISO(row[6]);
    const key=Object.keys(W).find(k=>k>=r0&&k<=r6);          // 该周行是否含某周报的 week_end
    const w=key?W[key]:null, rs=w&&w.range?w.range[0]:null, re=w&&w.range?w.range[1]:key;
    const cells=row.map(d=>{const iso=localISO(d);
      const out=d.getMonth()!==CALM?"out":"";
      const rep=w&&((rs&&re&&iso>=rs&&iso<=re)||iso===key)?"rep":"";
      return `<div class="cal-day ${out} ${rep}">${d.getDate()}</div>`;}).join("");
    const cls=key?`has ${key===WEEKSEL?"on":""}`:"", oc=key?`onclick="selectWeek('${key}')"`:"";
    rows+=`<div class="cal-wk ${cls}" ${oc}>${cells}</div>`;
    cur.setDate(cur.getDate()+7);
  }
  document.getElementById("calgrid").innerHTML=rows;
  document.getElementById("callabel").textContent=`${CALY} 年 ${CALM+1} 月`;
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
  document.getElementById("weeklybox").innerHTML=weeklyNav();
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
window.addEventListener("keydown",e=>{if(e.key==="Escape")closeWeekPage();});
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
