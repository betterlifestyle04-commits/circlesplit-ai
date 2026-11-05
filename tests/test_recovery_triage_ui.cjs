"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const {presentation}=require("../static/recovery_triage.js");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const start=html.indexOf("function renderRecoveryRisk(data){");
const end=html.indexOf("async function loadRecovery(",start);
assert(start>0&&end>start,"Recovery overview controller missing");
const source=html.slice(start,end);
const keys=["inconsistent_local_record","unknown_order_creation",
 "uncertain_capture_attempt","awaiting_provider_confirmation","locally_completed"];
function risk(){
 return {
  mode:"PAYPAL_SANDBOX",source:"current_local_sqlite_only",
  status:"needs_manual_review",total_records:5,attention_count:4,
  priority_review_count:3,older_than_60_minutes:2,
  unparseable_created_timestamps:0,unverified_request_face_value_cents:4400,
  categories:{
   inconsistent_local_record:1,unknown_order_creation:1,
   uncertain_capture_attempt:1,awaiting_provider_confirmation:1,
   locally_completed:1
  },
  notice:"No provider call"
 };
}

test("Activity exposes an accessible read-only all-ledger risk overview",()=>{
 assert.match(html,/id="recovery-risk-status" role="status" aria-live="polite"/);
 assert.match(html,/id="recovery-risk-metrics"/);
 assert.match(html,/id="recovery-risk-disclosure"/);
 assert.match(html,/script src="\/static\/recovery_triage\.js"/);
 assert.match(html,/risk: triage|renderRecoveryRisk\(d\.risk\)/);
});

test("presenter labels ambiguous orders distinctly from completed captures",()=>{
 const x=presentation(risk());
 assert.equal(x.heading,"Manual investigation needed");
 assert.equal(x.severity,"orange");
 assert.deepEqual(x.facts,[
  ["Unknown order creation",1],
  ["Capture attempt uncertain",1],
  ["Local ledger anomalies",1],
  ["Awaiting provider confirmation",1],
  ["Older than 60 min (unresolved)",2],
  ["Locally completed with capture ID",1]
 ]);
 assert.equal(x.faceValue,"$44.00");
 assert.match(x.disclosure,/NOT money collected, lost, or owed/);
 assert.match(x.disclosure,/never retry/);
});

test("empty and pending-only risk summaries are not labelled payment failures",()=>{
 const zero=risk();
 zero.categories=Object.fromEntries(keys.map(k=>[k,0]));
 Object.assign(zero,{status:"no_local_unresolved_records",total_records:0,
  attention_count:0,priority_review_count:0,older_than_60_minutes:0,
  unverified_request_face_value_cents:0});
 assert.equal(presentation(zero).heading,"No unresolved local orders");
 zero.categories.awaiting_provider_confirmation=1;
 Object.assign(zero,{status:"pending_provider_confirmation",total_records:1,
  attention_count:1,unverified_request_face_value_cents:1100});
 assert.equal(presentation(zero).heading,"Pending Sandbox verification");
});

test("tampered categories, totals, unsafe money and labels are rejected",()=>{
 const bad=[
  {mode:"LIVE"},
  {source:"provider_confirmed"},
  {status:"locally_settled"},
  {total_records:6},
  {attention_count:9},
  {priority_review_count:9},
  {older_than_60_minutes:5},
  {unparseable_created_timestamps:100},
  {unverified_request_face_value_cents:Infinity},
  {unverified_request_face_value_cents:"4400"},
  {categories:{...risk().categories,unknown_order_creation:9999}},
  {categories:{...risk().categories,extra:"<script>alert(1)</script>"}},
 ];
 for(const patch of bad)assert.throws(()=>presentation({...risk(),...patch}));
 assert.throws(()=>presentation(null));
});

function domHarness(input){
 const elements=new Map();
 const el=id=>{
  if(!elements.has(id))elements.set(id,{
   textContent:"",innerHTML:"",className:""
  });
  return elements.get(id);
 };
 const context=vm.createContext({
  el,window:{CircleSplitRecoveryTriage:{presentation}},
  safe:s=>String(s).replace(/</g,"&lt;").replace(/>/g,"&gt;"),
  Error
 });
 vm.runInContext(source,context,{timeout:1500});
 vm.runInContext("renderRecoveryRisk",context)(input);
 return {el};
}

test("Activity renders aggregate numbers and no provider references or IDs",()=>{
 const v=risk();
 v.notice="<script>steal()</script>";
 const h=domHarness(v);
 const markup=h.el("recovery-risk-metrics").innerHTML;
 assert.match(h.el("recovery-risk-status").textContent,/Manual investigation/);
 assert.match(markup,/Unverified request face value: \$44\.00/);
 assert.match(markup,/Unparseable local timestamps: 0/);
 assert.match(markup,/Capture attempt uncertain/);
 assert(!markup.includes("<script>"));
 assert(!markup.includes("paypal.com"));
 assert.match(h.el("recovery-risk-disclosure").textContent,/current local Sandbox records/);
});

test("broken response fails closed while keeping manual recovery instructions",()=>{
 const h=domHarness({...risk(),attention_count:100});
 assert.match(h.el("recovery-risk-status").textContent,/unavailable/);
 assert.equal(h.el("recovery-risk-metrics").textContent,"");
 assert.match(h.el("recovery-risk-disclosure").textContent,/No new payment/);
});
