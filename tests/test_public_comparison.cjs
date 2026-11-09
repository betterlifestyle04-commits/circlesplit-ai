"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const scenarios=require("../static/public_scenarios.js");
const validator=require("../static/public_portability.js");

function sample(){
 return {next:100,events:[{
  id:1,name:"Fictional volleyball",date:"2026-11-06",
  strategy:"equal",
  expenses:[{id:2,title:"Court",cents:100},{id:3,title:"Snacks",cents:1}],
  people:[
   {id:12,name:"Sam",weight:1,share_cents:33,approved:true,status:"unpaid"},
   {id:10,name:"Alex",weight:2,share_cents:34,approved:true,status:"demo_paid"},
   {id:11,name:"Taylor",weight:1,share_cents:34,approved:false,status:"unpaid"}
  ]
 }]};
}
function copy(){
 return scenarios.duplicateAsDraft(sample(),1,validator).model;
}
test("read-only compare reports exact baseline and alternative metrics, including simulated-only counts",()=>{
 const data=copy();
 const original=JSON.stringify(data);
 const result=scenarios.compareEvents(data,1,101,validator);
 assert.deepEqual(result,{
  mode:"BROWSER_LOCAL_FICTIONAL_COMPARISON",
  read_only:true,
  before:{
   id:1,name:"Fictional volleyball",strategy:"equal",
   budget_cents:101,participants:3,expenses:2,
   highest_share_cents:34,lowest_share_cents:33,
   approved_count:2,simulated_count:1
  },
  after:{
   id:101,name:"Fictional volleyball (what-if draft)",strategy:"equal",
   budget_cents:101,participants:3,expenses:2,
   highest_share_cents:34,lowest_share_cents:33,
   approved_count:0,simulated_count:0
  },
  delta:{
   budget_cents:0,participants:0,expenses:0,
   highest_share_cents:0,lowest_share_cents:0,
   approved_count:-2,simulated_count:-1
  }
 });
 assert.equal(JSON.stringify(data),original,"Comparison must not mutate model");
});

test("changes in the alternative budget and strategy produce exact signed cent differences",()=>{
 const data=copy();
 const alt=data.events[0];
 alt.strategy="weighted";
 alt.expenses[0].cents=200; // now 201 total
 // New ID order: Sam (1), Alex (2), Taylor (1)
 alt.people.forEach((p,i)=>{p.share_cents=[50,101,50][i]});
 const expected=validator.validateModel(data);
 const result=scenarios.compareEvents(expected,1,101,validator);
 assert.equal(result.after.strategy,"weighted");
 assert.equal(result.after.budget_cents,201);
 assert.equal(result.delta.budget_cents,100);
 assert.equal(result.delta.highest_share_cents,67);
 assert.equal(result.delta.lowest_share_cents,17);
 assert.equal(result.delta.participants,0);
 assert.equal(result.delta.simulated_count,-1);
});

test("adding an attendee to an alternative recalculates aggregate range without name matching",()=>{
 const data=copy();
 const draft=data.events[0];
 const newId=++data.next;
 draft.people.push({
  id:newId,name:"Alex",weight:1,share_cents:0,
  approved:false,status:"unpaid"
 });
 // Candidate with four participants, 101/4 = 26,25,25,25
 draft.people.forEach((p,i)=>{p.share_cents=[26,25,25,25][i]});
 const compare=scenarios.compareEvents(data,1,101,validator);
 assert.equal(compare.after.participants,4);
 assert.equal(compare.delta.participants,1);
 assert.equal(compare.after.highest_share_cents,26);
 assert.equal(compare.delta.highest_share_cents,-8);
 assert.equal(compare.after.lowest_share_cents,25);
 assert.equal(compare.delta.lowest_share_cents,-8);
 assert.equal(compare.before.approved_count,2);
 assert.equal(compare.after.approved_count,0);
});

test("events with no participants report null individual share metrics instead of fictional zero",()=>{
 const data={next:7,events:[
  {id:1,name:"First empty group",date:"2026-11-06",
   strategy:"equal",expenses:[],people:[]},
  {id:2,name:"Planning only event",date:"2026-11-06",
   strategy:"weighted",expenses:[{id:3,title:"Room hire",cents:5000}],people:[]}
 ]};
 const result=scenarios.compareEvents(data,1,2,validator);
 assert.equal(result.before.highest_share_cents,null);
 assert.equal(result.after.lowest_share_cents,null);
 assert.equal(result.delta.highest_share_cents,null);
 assert.equal(result.delta.lowest_share_cents,null);
 assert.equal(result.delta.budget_cents,5000);
 assert.equal(result.delta.participants,0);
});

test("missing comparison events, self-comparison and invalid dataset fail closed",()=>{
 const data=copy(),before=JSON.stringify(data);
 for(const args of [[1,1],[99,101],[1,99],["1",101],[1,NaN],[null,101]]){
  assert.throws(()=>scenarios.compareEvents(data,...args,validator));
 }
 assert.throws(()=>scenarios.compareEvents(data,1,101,null),/validator unavailable/);
 assert.equal(JSON.stringify(data),before);
 const bad=copy();
 bad.events[0].people[0].share_cents=999;
 assert.throws(()=>scenarios.compareEvents(bad,1,101,validator),/exact-cent|Invalid fictional participant state/);
 const tampered=copy();
 tampered.events[0].paypal_order_id="PAYPAL-NOT-ALLOWED";
 assert.throws(()=>scenarios.compareEvents(tampered,1,101,validator),/fields/);
});

test("swapping baseline and alternative reverses every comparable delta",()=>{
 const data=copy();
 const a=scenarios.compareEvents(data,1,101,validator);
 const b=scenarios.compareEvents(data,101,1,validator);
 for(const key of Object.keys(a.delta))
  assert.equal(a.delta[key]+b.delta[key],0);
 assert.equal(a.before.id,b.after.id);
 assert.equal(a.after.id,b.before.id);
});

test("comparison does not read provider records or claim real payment confirmation",()=>{
 const source=String(scenarios.compareEvents);
 assert.doesNotMatch(source,/\bfetch\s*\(|paypal|payment_verified|capture_id/);
 const data=copy();
 const status=scenarios.compareEvents(data,1,101,validator);
 assert.equal(status.mode,"BROWSER_LOCAL_FICTIONAL_COMPARISON");
 assert(!("capture_id" in status.before));
 assert(!("order_id" in status.after));
 assert(!("verified_payments" in status.delta));
});


test("share-cap analysis matches strict integer-cent boundaries without changing the model",()=>{
 const data=copy();
 const untouched=JSON.stringify(data);
 const equal=scenarios.compareAffordability(data,1,101,34,validator);
 assert.deepEqual(equal,{
  mode:"BROWSER_LOCAL_FICTIONAL_AFFORDABILITY",read_only:true,cap_cents:34,
  before:{participants:3,over_cap_people:0,maximum_excess_cents:0},
  after:{participants:3,over_cap_people:0,maximum_excess_cents:0},
  delta:{over_cap_people:0,maximum_excess_cents:0},
  notice:"Fictional share estimates, not actual affordability, consent, or payments."
 });
 const justBelow=scenarios.compareAffordability(data,1,101,33,validator);
 assert.equal(justBelow.before.over_cap_people,2);
 assert.equal(justBelow.after.over_cap_people,2);
 assert.equal(justBelow.before.maximum_excess_cents,1);
 assert.equal(JSON.stringify(data),untouched);
});

test("weighted what-if compares the number above cap, not participant identities",()=>{
 const data=copy(),draft=data.events[0];
 draft.strategy="weighted";
 draft.expenses[0].cents=200;
 draft.people.forEach((p,i)=>p.share_cents=[50,101,50][i]);
 const report=scenarios.compareAffordability(data,1,101,50,validator);
 assert.equal(report.before.over_cap_people,0);
 assert.equal(report.after.over_cap_people,1);
 assert.equal(report.delta.over_cap_people,1);
 assert.equal(report.before.maximum_excess_cents,0);
 assert.equal(report.after.maximum_excess_cents,51);
 assert.equal(report.delta.maximum_excess_cents,51);
 assert(!("names" in report));
 assert(!("payments" in report));
});

test("empty groups do not invent share values or claim affordable participants",()=>{
 const data={next:3,events:[
  {id:1,name:"Zero participants",date:"2026-11-09",strategy:"equal",
   expenses:[{id:3,title:"Fictional hall",cents:1000}],people:[]},
  {id:2,name:"Other empty group",date:"2026-11-09",strategy:"weighted",
   expenses:[],people:[]}
 ]};
 const report=scenarios.compareAffordability(data,1,2,1200,validator);
 assert.equal(report.before.participants,0);
 assert.equal(report.after.over_cap_people,0);
 assert.equal(report.before.maximum_excess_cents,null);
 assert.equal(report.after.maximum_excess_cents,null);
 assert.equal(report.delta.maximum_excess_cents,null);
});

test("invalid cap, self-comparison, missing events and tampered data fail closed",()=>{
 const data=copy(),before=JSON.stringify(data);
 for(const cap of [0,-1,1.5,NaN,Infinity,"1200",null,true,10000001]){
  assert.throws(()=>scenarios.compareAffordability(data,1,101,cap,validator));
 }
 for(const ids of [[1,1],[1,999],[999,101],["1",101],[null,101]]){
  assert.throws(()=>scenarios.compareAffordability(data,...ids,1200,validator));
 }
 assert.throws(()=>scenarios.compareAffordability(data,1,101,1200,null),
   /validator unavailable/);
 const invalid=copy();
 invalid.events[0].people[0].share_cents=999;
 assert.throws(()=>scenarios.compareAffordability(invalid,1,101,1200,validator));
 assert.equal(JSON.stringify(data),before);
});

test("affordability analysis is strictly browser-local and anonymous",()=>{
 const src=String(scenarios.compareAffordability);
 for(const forbidden of [/\bfetch\s*\(/,/\blocalStorage\b/,/paypal\.com/,
   /order_id/,/capture_id/,/buyer_email/,/approve\(/]){
  assert.doesNotMatch(src,forbidden);
 }
 const data=copy();
 const report=scenarios.compareAffordability(data,1,101,50,validator);
 for(const forbidden of ["Sam","Alex","Taylor","idempotency","capture_id","order_id"]){
  assert(!JSON.stringify(report).includes(forbidden),forbidden);
 }
 assert.equal(report.read_only,true);
});


test("anonymous copied report uses only validated fixed-field, exact-cent totals",()=>{
 const data=copy(),before=JSON.stringify(data);
 const text=scenarios.formatAnonymousComparison(data,1,101,34,validator);
 assert.match(text,/FICTIONAL browser-only scenario summary/);
 assert.match(text,/Per-person limit: \$0\.34/);
 assert.match(text,/Baseline: equal split; budget \$1\.01; participants 3;/);
 assert.match(text,/Alternative: equal split; budget \$1\.01; participants 3;/);
 assert.match(text,/above cap 0\/3; maximum excess \$0\.00/);
 assert.match(text,/Alternative minus baseline: total budget \$0\.00/);
 assert.match(text,/NOT VERIFIED: real affordability, attendance, Gemini API, PayPal Sandbox orders\/captures/);
 assert.equal(JSON.stringify(data),before);
 for(const privateValue of ["Fictional volleyball","Sam","Alex","Taylor",
  "Court","Snacks","demo_paid","capture_id","order_id","request_id"]){
  assert(!text.includes(privateValue),"must not copy "+privateValue);
 }
});

test("anonymous summary accurately reports over-cap count and signed money deltas",()=>{
 const data=copy(),draft=data.events[0];
 draft.strategy="weighted";
 draft.expenses[0].cents=200;
 draft.people.forEach((p,i)=>p.share_cents=[50,101,50][i]);
 const text=scenarios.formatAnonymousComparison(data,1,101,50,validator);
 assert.match(text,/Baseline: equal split; budget \$1\.01/);
 assert.match(text,/Alternative: weighted split; budget \$2\.01/);
 assert.match(text,/above cap 1\/3; maximum excess \$0\.51/);
 assert.match(text,/total budget \+\$1\.00; participants 0; people above cap \+1; maximum excess \+\$0\.51/);
 const backwards=scenarios.formatAnonymousComparison(data,101,1,50,validator);
 assert.match(backwards,/total budget -\$1\.00; participants 0; people above cap -1; maximum excess -\$0\.51/);
});

test("anonymous summary preserves not-applicable state for empty groups",()=>{
 const data={next:3,events:[
  {id:1,name:"UNTRUSTED_PRIVATE_NAME",date:"2026-11-09",strategy:"equal",
   expenses:[{id:3,title:"Private expense",cents:1000}],people:[]},
  {id:2,name:"Another PRIVATE NAME",date:"2026-11-09",strategy:"weighted",
   expenses:[],people:[]}
 ]};
 const text=scenarios.formatAnonymousComparison(data,1,2,1200,validator);
 assert.match(text,/highest share not applicable; lowest share not applicable/);
 assert.match(text,/above cap 0\/0; maximum excess not applicable/);
 assert.match(text,/total budget -\$10\.00/);
 assert.match(text,/maximum excess not comparable/);
 assert(!text.includes("PRIVATE"));
});

test("anonymous copy fails on invalid states and never calls a provider",()=>{
 const data=copy(),before=JSON.stringify(data);
 assert.throws(()=>scenarios.formatAnonymousComparison(data,1,101,0,validator));
 assert.throws(()=>scenarios.formatAnonymousComparison(data,1,1,100,validator));
 assert.throws(()=>scenarios.formatAnonymousComparison(data,1,101,100,null));
 const broken=copy();
 broken.events[0].paypal_order_id="PRIVATE-PAYMENT";
 assert.throws(()=>scenarios.formatAnonymousComparison(broken,1,101,100,validator));
 assert.equal(JSON.stringify(data),before);
 const source=String(scenarios.formatAnonymousComparison);
 for(const prohibited of [/\bfetch\s*\(/,/\blocalStorage\b/,/paypal\.com/,
   /navigator/,/clipboard/,/order_id/,/capture_id/,/\.name\b/,/\.id\b/])
  assert.doesNotMatch(source,prohibited);
});
