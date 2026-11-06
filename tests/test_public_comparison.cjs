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
