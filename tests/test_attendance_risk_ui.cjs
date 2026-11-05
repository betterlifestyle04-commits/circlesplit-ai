"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const start=html.indexOf("function resetAttendanceRisk(){");
const end=html.indexOf("async function previewScenario(",start);
assert.ok(start>0&&end>start,"Attendance stress controller not found");
const script=html.slice(start,end);

function response(){
 return {
  event_id:7,mode:"SANDBOX_PLANNING_ONLY",read_only:true,
  strategy:"equal",scenario_rule:"retain_highest_weight_remove_next_highest",
  cap_cents:1200,budget_cents:22000,current_people:20,
  current_largest_share_cents:1100,requested_maximum_absent:2,
  tested_maximum_absent:2,approved_people:0,has_existing_sandbox_orders:false,
  first_target_breach_at_absences:2,
  projections:[
   {absent_people:0,remaining_people:20,largest_share_cents:1100,
    smallest_share_cents:1100,largest_share_increase_cents:0,over_target:false,
    replacements_feasible:true,minimum_replacements_needed:0,
    best_replacement_count:0,best_replacement_largest_share_cents:1100,
    replacement_gap_cents:0,maximum_replacements_considered:50,
    replacement_candidates_tested:1},
   {absent_people:1,remaining_people:19,largest_share_cents:1158,
    smallest_share_cents:1157,largest_share_increase_cents:58,over_target:false,
    replacements_feasible:true,minimum_replacements_needed:0,
    best_replacement_count:0,best_replacement_largest_share_cents:1158,
    replacement_gap_cents:0,maximum_replacements_considered:50,
    replacement_candidates_tested:1},
   {absent_people:2,remaining_people:18,largest_share_cents:1223,
    smallest_share_cents:1222,largest_share_increase_cents:123,over_target:true,
    replacements_feasible:true,minimum_replacements_needed:1,
    best_replacement_count:1,best_replacement_largest_share_cents:1158,
    replacement_gap_cents:0,maximum_replacements_considered:50,
    replacement_candidates_tested:2}
  ],notice:"Read-only no-show preview, no state changes."
 };
}
function harness({result=response(),selected=7,requestError=null}={}){
 const elements=new Map(),calls=[],messages=[];
 let eventId=selected;
 function el(id){
  if(!elements.has(id)){
   elements.set(id,{
    id,disabled:false,innerHTML:"",textContent:"",className:"",
    value:({"attendance-risk-cap":"12.00","attendance-risk-absent":"2",
      "attendance-risk-strategy":"equal"})[id]??""
   });
  }
  return elements.get(id);
 }
 const context=vm.createContext({
  el,
  event:()=>eventId===null?null:{id:eventId},
  post:async(url,body)=>{
   calls.push({url,body});
   if(requestError)throw Error(requestError);
   return typeof result==="function"?await result():result;
  },
  notice:(...args)=>messages.push(args),
  money:amount=>"$"+(amount/100).toFixed(2),
  safe:input=>String(input).replace(/&/g,"&amp;")
      .replace(/</g,"&lt;").replace(/>/g,"&gt;")
      .replace(/"/g,"&quot;"),
  Number,String,Error,Math,Array,JSON
 });
 vm.runInContext(script,context,{timeout:2000});
 return {
  run:vm.runInContext("previewAttendanceRisk",context),
  reset:vm.runInContext("resetAttendanceRisk",context),
  el,calls,messages,choose:id=>eventId=id
 };
}
const evt=()=>({preventDefault(){}});

test("Scenario Lab includes an accessible, explicitly hypothetical no-show form",()=>{
 for(const id of ["attendance-risk-form","attendance-risk-cap","attendance-risk-absent",
                  "attendance-risk-strategy","attendance-risk-run",
                  "attendance-risk-target"]){
  assert.match(html,new RegExp('id="'+id+'"'));
 }
 assert.match(html,/id="attendance-risk-results"[^>]*role="status"/);
 assert.match(html,/el\("attendance-risk-form"\).addEventListener\("submit",previewAttendanceRisk\)/);
 assert.match(html,/resetAffordability\(\);resetAttendanceRisk\(\);render\(\)/);
 assert.match(html,/one adverse scenario, not a forecast or proven worst case/i);
});

test("preview uses only protected read-only planning endpoint and renders exact cents",async()=>{
 const h=harness();
 await h.run(evt());
 assert.equal(h.calls.length,1);
 assert.equal(h.calls[0].url,"/api/events/7/attendance-risk");
 assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].body)),{
  max_share:"12.00",maximum_absent:2,strategy:"equal"
 });
 assert.match(h.el("attendance-risk-results").innerHTML,/Target breached once 2 attendee/);
 assert.match(h.el("attendance-risk-results").innerHTML,/\$12\.23/);
 assert.match(h.el("attendance-risk-results").innerHTML,/Above cap/);
 assert.match(h.el("attendance-risk-results").innerHTML,/Possible recovery/);
 assert.match(h.el("attendance-risk-results").innerHTML,/adding 1 hypothetical attendee/);
 assert.match(h.el("attendance-risk-results").innerHTML,/Extra attendees to restore cap/);
 assert.match(h.el("attendance-risk-results").innerHTML,/\+1 hypothetical/);
 assert.equal(h.el("attendance-risk-run").disabled,false);
 assert.equal(h.messages.at(-1)[1],false);
 assert.doesNotMatch(script,/\/api\/paypal\/orders|\/api\/paypal\/capture/);
});

test("already-over-target warning and checkout lock are explicit",async()=>{
 const d=response();
 d.first_target_breach_at_absences=0;
 d.has_existing_sandbox_orders=true;
 d.projections.forEach(x=>{x.over_target=true;});
 const h=harness({result:d});
 await h.run(evt());
 assert.match(h.el("attendance-risk-results").innerHTML,/current roster already exceeds/i);
 assert.match(h.el("attendance-risk-results").innerHTML,/Sandbox checkout already started/);
});

test("unreachable target shows honest bounded failure instead of implying a charge",async()=>{
 const d=response();
 d.cap_cents=1;
 d.first_target_breach_at_absences=0;
 d.projections.forEach((r,i)=>{
  r.over_target=true;
  r.replacements_feasible=false;
  r.minimum_replacements_needed=null;
  r.best_replacement_count=50;
  r.best_replacement_largest_share_cents=[315,319,324][i];
  r.replacement_gap_cents=r.best_replacement_largest_share_cents-1;
  r.replacement_candidates_tested=51;
 });
 const h=harness({result:d});
 await h.run(evt());
 const rendered=h.el("attendance-risk-results").innerHTML;
 assert.match(rendered,/cannot be restored within 50 hypothetical extra attendee/);
 assert.match(rendered,/\$3\.14 above the cap/);
 assert.match(rendered,/Not achievable within \+50/);
 assert.equal(h.calls.length,1);
});

test("tampered replacement count is rejected as an invalid server response",async()=>{
 const d=response();
 d.projections[2].minimum_replacements_needed=200;
 const h=harness({result:d});
 await h.run(evt());
 assert.match(h.el("attendance-risk-results").textContent,/Invalid attendance risk preview/);
 assert.equal(h.messages.at(-1)[1],true);
});

test("missing event prevents request",async()=>{
 const h=harness({selected:null});
 await h.run(evt());
 assert.equal(h.calls.length,0);
 assert.match(h.messages[0][0],/select an event/);
});

test("switching events while request is in flight discards stale result",async()=>{
 let release;
 const pending=new Promise(r=>{release=r;});
 const h=harness({result:()=>pending});
 const started=h.run(evt());
 h.choose(8);
 release(response());
 await started;
 assert.equal(h.calls.length,1);
 assert.match(h.el("attendance-risk-results").textContent,/Enter assumptions/);
 assert.equal(h.messages.length,0);
 assert.equal(h.el("attendance-risk-run").disabled,false);
});

test("editing the no-show assumptions in flight discards previous preview",async()=>{
 let release;
 const pending=new Promise(r=>{release=r;});
 const h=harness({result:()=>pending});
 const started=h.run(evt());
 h.el("attendance-risk-cap").value="10.00";
 release(response());
 await started;
 assert.match(h.el("attendance-risk-results").textContent,/Enter assumptions/);
 assert.doesNotMatch(h.el("attendance-risk-results").innerHTML,/Target breached/);
});

test("malformed response is rejected rather than trusted",async()=>{
 const d=response();d.projections[1].largest_share_cents="USD 12";
 const h=harness({result:d});
 await h.run(evt());
 assert.match(h.el("attendance-risk-results").textContent,/Invalid attendance risk preview/);
 assert.equal(h.messages.at(-1)[1],true);
});

test("server notice is escaped and no script injection rendered",async()=>{
 const d=response();d.notice='<img src=x onerror=alert(1)>';
 const h=harness({result:d});
 await h.run(evt());
 const rendered=h.el("attendance-risk-results").innerHTML;
 assert(!rendered.includes("<img"));
 assert(rendered.includes("&lt;img"));
});

test("failed request leaves form usable and explains failure",async()=>{
 const h=harness({requestError:"Service offline"});
 await h.run(evt());
 assert.equal(h.el("attendance-risk-run").disabled,false);
 assert.equal(h.el("attendance-risk-run").textContent,"Stress-test attendance");
 assert.match(h.el("attendance-risk-results").textContent,/Service offline/);
});
