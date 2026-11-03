/* CircleSplit Insight Center: client-side reporting for the protected sandbox workspace. */
"use strict";
function insightData(events){
  const all = Array.isArray(events) ? events : [];
  let budget=0, funded=0, simulated=0, participants=0, approved=0, outstanding=0, errors=0;
  const breakdown = all.map(function(e){
    const total = Number(e.total_cents)||0;
    const confirmed = Number(e.sandbox_cents)||0;
    const simulatedAmount = Number(e.simulated_cents)||0;
    const members = Array.isArray(e.people)?e.people:[];
    const sumShares = members.reduce(function(s,p){return s+(Number(p.share_cents)||0)},0);
    const a = members.filter(function(p){return Boolean(p.approved)}).length;
    budget+=total; funded+=confirmed; simulated+=simulatedAmount; participants+=members.length; approved+=a;
    outstanding+=Math.max(0,total-confirmed);
    if(members.length>0 && sumShares!==total) errors++;
    return {id:e.id,name:e.name,date:e.date,people:members.length,approved:a,total:total,confirmed:confirmed,
            simulated:simulatedAmount,outstanding:Math.max(0,total-confirmed),balanced:members.length===0||sumShares===total};
  });
  return {count:all.length,budget,confirmed:funded,simulated,participants,approved,outstanding,
          issues:errors,rate:budget>0?Math.round(100*funded/budget):0,events:breakdown};
}
function csvCell(value){
  let s=String(value==null?"":value);
  if(/^\s*[=+\-@]/.test(s))s="'"+s; // spreadsheet formula injection defense
  return '"'+s.replace(/"/g,'""')+'"';
}
function csvText(rows){return "\uFEFF"+rows.map(function(row){return row.map(csvCell).join(",")}).join("\r\n")+"\r\n"}
function offerDownload(filename, text, contentType){
  const blob=new Blob([text],{type:contentType});
  const url=URL.createObjectURL(blob);
  const a=document.createElement("a");a.href=url;a.download=filename;a.style.display="none";
  document.body.appendChild(a);a.click();a.remove();
  window.setTimeout(function(){URL.revokeObjectURL(url)},500);
}
function exportSelectedShares(){
  const e=event();
  if(!e){notice("Create or select an event to export.",true);return;}
  const rows=[["Event","Date","Participant","Weight","Share USD","Approved","Status"]];
  (e.people||[]).forEach(function(p){rows.push([e.name,e.date,p.name,p.weight,(Number(p.share_cents)/100).toFixed(2),p.approved?"Yes":"No",p.status])});
  offerDownload("circlesplit-event-"+e.id+"-shares.csv",csvText(rows),"text/csv;charset=utf-8");
  notice("CSV share report downloaded. It includes fictional participant names, not PayPal secrets.",false);
}
function exportFundingReport(){
  const d=insightData(state.events);
  const rows=[["Event","Date","Participants","Approvals","Budget USD","Verified sandbox USD","Simulated USD","Outstanding USD","Allocation balanced"]];
  d.events.forEach(function(e){rows.push([e.name,e.date,e.people,e.approved,(e.total/100).toFixed(2),(e.confirmed/100).toFixed(2),
     (e.simulated/100).toFixed(2),(e.outstanding/100).toFixed(2),e.balanced?"Yes":"No"])});
  offerDownload("circlesplit-funding-report.csv",csvText(rows),"text/csv;charset=utf-8");
  notice("Funding CSV downloaded. Amounts are sandbox-only and demo data may reset after a deploy.",false);
}
function exportDemoSnapshot(){
  const snapshot={
    app:"CircleSplit AI",kind:"read-only sandbox demonstration snapshot",schema_version:1,
    exported_at:new Date().toISOString(),currency:"USD",storage:"ephemeral SQLite on Render Free",
    warning:"This export is for review only, NOT a restorable database backup or proof of real-money payment.",
    events:(state.events||[]).map(function(e){return {
      name:e.name,date:e.date,note:e.note,strategy:e.strategy,total_cents:e.total_cents,
      verified_sandbox_cents:e.sandbox_cents,simulated_cents:e.simulated_cents,
      expenses:(e.expenses||[]).map(function(x){return {title:x.title,cents:x.cents}}),
      people:(e.people||[]).map(function(p){return {name:p.name,weight:p.weight,share_cents:p.share_cents,approved:Boolean(p.approved),status:p.status}})
    }}),
    transactions:(window.circleTransactions||[]).map(function(p){return {
      event_name:p.event_name,person_name:p.person_name,amount_cents:p.amount_cents,status:p.status,created:p.created
    }})
  };
  offerDownload("circlesplit-sandbox-snapshot.json",JSON.stringify(snapshot,null,2),"application/json;charset=utf-8");
  notice("Read-only JSON snapshot downloaded. It deliberately excludes PayPal order IDs, capture IDs and API secrets.",false);
}
function renderInsights(){
  const box=document.getElementById("insights-metrics"),tbody=document.getElementById("insights-events");
  if(!box||!tbody)return;
  const d=insightData(state.events);
  const cells=[
    ["Group budgets",money(d.budget),"Across "+d.count+" fictional events"],
    ["Verified sandbox",money(d.confirmed),d.rate+"% of total budgets"],
    ["Outstanding",money(d.outstanding),"Not confirmed by PayPal"],
    ["Approvals",d.approved+" / "+d.participants,"Participant share approvals"]
  ];
  box.innerHTML=cells.map(function(x){return '<div class="card"><div class="metric-label">'+safe(x[0])+'</div><div class="metric-value">'+safe(x[1])+'</div><div class="metric-foot">'+safe(x[2])+'</div></div>'}).join("");
  tbody.innerHTML=d.events.length?d.events.map(function(e){
    const pct=e.total?Math.min(100,Math.round(e.confirmed/e.total*100)):0;
    return '<tr><td><b>'+safe(e.name)+'</b><div class="muted small">'+safe(e.date)+'</div></td>'+
      '<td>'+e.people+'</td><td>'+money(e.total)+'</td><td>'+money(e.confirmed)+
      '<div class="progress" style="margin-top:7px"><div class="fill" style="width:'+pct+'%"></div></div></td>'+
      '<td>'+money(e.outstanding)+'</td><td><span class="pill '+(e.balanced?"":"orange")+'">'+(e.balanced?"Balanced":"Check shares")+'</span></td></tr>';
  }).join(""):'<tr><td colspan="6" class="muted">No events yet. Create an event to see funding analytics.</td></tr>';
  const note=document.getElementById("insights-note");
  if(note)note.textContent=d.issues?
    "Attention: "+d.issues+" event allocation(s) do not sum to their budgets. Do not collect any additional test payments until this is resolved.":
    "All populated event allocations sum to their budgets. Only confirmed PayPal SANDBOX captures count as verified; simulated payments are excluded. Reporting is based on the current ephemeral demo data.";
}
if(typeof module!=="undefined"&&module.exports){module.exports={insightData,csvCell,csvText};}
