"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const start=html.indexOf("function resetAffordability(){");
const end=html.indexOf("function signedMoney(",start);
assert.ok(start>0&&end>start,"Affordability UI controller was not found");
const script=html.slice(start,end);

function response(feasible=true){
 return {
  event_id:7,mode:"SANDBOX_PLANNING_ONLY",read_only:true,strategy:"equal",
  feasible,cap_cents:1000,budget_cents:22000,current_people:20,
  current_largest_share_cents:1100,minimum_additional_people:feasible?2:null,
  tested_maximum_extra_people:feasible?2:1,remaining_largest_share_gap_cents:feasible?0:48,
  recommendation:{
   additional_people:feasible?2:1,total_people:feasible?22:21,
   largest_share_cents:feasible?1000:1048,
   smallest_share_cents:feasible?1000:1047
  },has_existing_sandbox_orders:false,approved_people:0,
  notice:"Advisory only. No event or PayPal state changed."
 };
}
function harness({result=response(),selected=7,requestError=null}={}){
 const elements=new Map(),calls=[],messages=[];
 let eventId=selected;
 function el(id){
  if(!elements.has(id)){
   elements.set(id,{
    id,disabled:false,innerHTML:"",textContent:"",className:"",
    value:({"affordability-cap":"10.00","affordability-extra":"50",
      "affordability-strategy":"equal"})[id]??""
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
  Number,String,Error
 });
 vm.runInContext(script,context,{timeout:2000});
 return {
  run:vm.runInContext("previewAffordability",context),
  reset:vm.runInContext("resetAffordability",context),
  el,calls,messages,choose:id=>eventId=id
 };
}
const evt=()=>({preventDefault(){}});

test("Scenario Lab includes an accessible self-contained affordability form",()=>{
 assert.match(html,/id="affordability-form"/);
 for(const id of ["affordability-cap","affordability-extra",
                  "affordability-strategy","affordability-run"]) {
  assert.match(html,new RegExp('id="'+id+'"'));
 }
 assert.match(html,/id="affordability-results"[^>]*role="status"/);
 assert.match(html,/el\("affordability-form"\).addEventListener\("submit",previewAffordability\)/);
 assert.match(html,/resetAffordability\(\);render\(\)/);
 assert.match(html,/maximum extra/i);
});

test("affordable scenario only posts to read-only planning API",async()=>{
 const h=harness();
 await h.run(evt());
 assert.equal(h.calls.length,1);
 assert.equal(h.calls[0].url,"/api/events/7/affordability");
 assert.deepEqual(JSON.parse(JSON.stringify(h.calls[0].body)),{
  max_share:"10.00",maximum_extra_people:50,strategy:"equal"
 });
 assert.match(h.el("affordability-results").innerHTML,/Within target: 2 additional attendee/);
 assert.match(h.el("affordability-results").innerHTML,/Projected largest share/);
 assert.match(h.el("affordability-results").innerHTML,/\$10\.00/);
 assert.equal(h.el("affordability-run").disabled,false);
 assert.equal(h.messages.at(-1)[1],false);
});

test("unaffordable scenario is explicitly labelled, including the remaining gap",async()=>{
 const h=harness({result:response(false)});
 await h.run(evt());
 const rendered=h.el("affordability-results").innerHTML;
 assert.match(rendered,/Further changes needed/);
 assert.match(rendered,/Not achievable within 1 additional attendee/);
 assert.match(rendered,/\$0\.48 above your target/);
 assert.equal(h.calls.length,1);
});

test("existing sandbox order warns about locked budgets but performs no payment requests",async()=>{
 const d=response(true);d.has_existing_sandbox_orders=true;
 const h=harness({result:d});
 await h.run(evt());
 assert.match(h.el("affordability-results").innerHTML,/Sandbox checkout already started/);
 assert.equal(h.calls.length,1);
 assert(!h.calls[0].url.includes("paypal"));
 assert.doesNotMatch(script,/\/api\/paypal\/orders|\/api\/paypal\/capture/);
});

test("missing event does not invoke a preview request",async()=>{
 const h=harness({selected:null});
 await h.run(evt());
 assert.equal(h.calls.length,0);
 assert.match(h.messages[0][0],/select an event/);
});

test("switching event while request is in flight discards result",async()=>{
 let release;
 const pending=new Promise(r=>{release=r});
 const h=harness({result:()=>pending});
 const started=h.run(evt());
 h.choose(9);
 release(response(true));
 await started;
 assert.match(h.el("affordability-results").textContent,/Choose your target|Enter your target/);
 assert.equal(h.calls.length,1);
 assert.equal(h.el("affordability-run").disabled,false);
 assert(h.messages.some(m=>m[1]===true));
});

test("invalid response is not shown as an authoritative affordability result",async()=>{
 const d=response(true);d.mode="PAYPAL_LIVE";
 const h=harness({result:d});
 await h.run(evt());
 assert.match(h.el("affordability-results").textContent,/Invalid affordability preview response/);
 assert.equal(h.messages.at(-1)[1],true);
});

test("server-generated text is escaped rather than executed",async()=>{
 const d=response(true);d.notice='<img src=x onerror=alert(1)>';
 const h=harness({result:d});
 await h.run(evt());
 const rendered=h.el("affordability-results").innerHTML;
 assert(!rendered.includes("<img"));
 assert(rendered.includes("&lt;img"));
});

test("failed request leaves inputs usable and shows an error",async()=>{
 const h=harness({requestError:"Backend temporarily unavailable"});
 await h.run(evt());
 assert.equal(h.el("affordability-run").disabled,false);
 assert.equal(h.el("affordability-run").textContent,"Find affordable group size");
 assert.match(h.el("affordability-results").textContent,/temporarily unavailable/);
});
