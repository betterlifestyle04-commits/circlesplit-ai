"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const {presentation}=require("../static/webhook_audit.js");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const begin=html.indexOf("async function loadWebhookAudit(){");
const end=html.indexOf("async function runLedgerAudit(){",begin);
assert.ok(begin>=0 && end>begin,"Signed webhook audit function missing");
const code=html.slice(begin,end);
const KEYS=[
 "capture_recorded","capture_already_recorded","unmatched_order",
 "missing_order_reference","amount_or_currency_mismatch",
 "invalid_capture_payload","ignored_event_type","legacy_unclassified"
];

function valid(){
 return {
  mode:"PAYPAL_SANDBOX",source:"current_local_sqlite_signed_events_only",
  total_events:7,manual_review_events:4,
  outcomes:{
   capture_recorded:1,capture_already_recorded:1,unmatched_order:1,
   missing_order_reference:1,amount_or_currency_mismatch:1,
   invalid_capture_payload:1,ignored_event_type:1,legacy_unclassified:0
  },notice:"Local only"
 };
}

test("strict signed webhook presenter distinguishes locally verified captures from failures",()=>{
 const x=presentation(valid());
 assert.match(x.headline,/4 signed webhook event/);
 assert.equal(x.needsReview,true);
 assert.equal(x.rows.length,8);
 assert.equal(x.rows.find(y=>y.label==="Unknown local order").count,1);
 assert.equal(x.rows.find(y=>y.label==="Captured and verified locally").needsReview,false);
 assert.match(x.notice,/does not mean PayPal has no order/);
 assert.match(x.notice,/No provider lookup/);
});

test("empty local signed event list is not treated as proof of provider completeness",()=>{
 const x=valid();
 x.total_events=0;x.manual_review_events=0;
 x.outcomes=Object.fromEntries(KEYS.map(name=>[name,0]));
 const out=presentation(x);
 assert.match(out.headline,/No signed webhooks recorded/);
 assert.match(out.notice,/A missing database record/);
});

test("invalid counts, missing fields, unknown keys and injected values fail closed",()=>{
 const altered=[
  {mode:"LIVE"},
  {source:"paypal-confirmed"},
  {total_events:9},
  {manual_review_events:5},
  {total_events:"7"},
  {manual_review_events:-1},
  {outcomes:{...valid().outcomes,unmatched_order:Infinity}},
  {outcomes:{...valid().outcomes,unmatched_order:"1"}},
  {outcomes:{...valid().outcomes,extra:"<img onerror=alert(1)>"}},
 ];
 for(const item of altered)
  assert.throws(()=>presentation({...valid(),...item}));
 assert.throws(()=>presentation(null));
 assert.throws(()=>presentation({...valid(),outcomes:{}}));
});

function harness(response=valid(),failure=null){
 const nodes=new Map();
 function el(id){
  if(!nodes.has(id))nodes.set(id,{
   disabled:false,textContent:"",children:[],
   replaceChildren(){this.children=[];this.textContent="";},
   appendChild(child){this.children.push(child);}
  });
  return nodes.get(id);
 }
 const calls=[];
 const context=vm.createContext({
  el,document:{createElement:tag=>({tag,textContent:"",className:""})},
  window:{CircleSplitWebhookAudit:{presentation}},
  request:async path=>{
   calls.push(["GET",path]);
   if(failure)throw Error(failure);
   return response;
  },Error
 });
 vm.runInContext(code,context,{timeout:2000});
 return {load:vm.runInContext("loadWebhookAudit",context),el,calls};
}

test("Activity uses GET only, text nodes and accessible status",async()=>{
 assert.match(html,/id="webhook-audit-status" role="status" aria-live="polite"/);
 assert.match(html,/onclick="loadWebhookAudit\(\)"/);
 assert.match(html,/script src="\/static\/webhook_audit\.js"/);
 const data=valid();
 data.notice="<script>ignore this server string</script>";
 const h=harness(data);
 await h.load();
 assert.deepEqual(h.calls,[["GET","/api/paypal/webhook-audit"]]);
 assert.match(h.el("webhook-audit-status").textContent,/4 signed webhook/);
 assert.equal(h.el("webhook-audit-metrics").children.length,8);
 assert.match(h.el("webhook-audit-metrics").children[2].textContent,/Unknown local order: 1/);
 assert.equal(h.el("webhook-audit-metrics").children[2].className,"pill orange");
 assert(!JSON.stringify(h.el("webhook-audit-metrics")).includes("<script>"));
 assert.match(h.el("webhook-audit-disclosure").textContent,/No provider lookup/);
 assert.equal(h.el("webhook-audit-run").disabled,false);
});

test("unexpected responses and network errors clear prior results and never POST",async()=>{
 for(const [response,error] of [
  [{...valid(),total_events:999},null],
  [valid(),"Connection unavailable"]
 ]){
  const h=harness(response,error);
  await h.load();
  assert.deepEqual(h.calls,[["GET","/api/paypal/webhook-audit"]]);
  assert.equal(h.el("webhook-audit-metrics").children.length,0);
  assert.match(h.el("webhook-audit-status").textContent,/unavailable/);
  assert.equal(h.el("webhook-audit-run").disabled,false);
 }
});

test("opening Activity triggers webhook audit without changing existing recovery",()=>{
 assert.match(html,/if\(tab==="activity"\)\{loadRecovery\(\);loadWebhookAudit\(\);\}/);
 assert.match(html,/if\(currentTab==="activity"\)\{await loadRecovery\(\);await loadWebhookAudit\(\);\}/);
});
