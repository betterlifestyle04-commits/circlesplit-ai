"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const {exactSplit,preview}=require("../static/public_recovery.js");

const html=fs.readFileSync(path.join(__dirname,"../static/public.html"),"utf8");
const people=n=>Array.from({length:n},(_,i)=>({id:i+10,weight:1}));

test("fictional local allocator reproduces exact largest-remainder cents",()=>{
 assert.deepEqual(exactSplit(1000,people(3),"equal"),[334,333,333]);
 assert.deepEqual(exactSplit(10001,[{id:1,weight:3},{id:2,weight:2},{id:3,weight:1}],"weighted"),
  [5000,3334,1667]);
 assert.equal(exactSplit(22000,people(20),"equal").reduce((a,b)=>a+b,0),22000);
});

test("no-show preview gives correct equal-split replacement actions without mutating participants",()=>{
 const p=people(20);const before=JSON.stringify(p);
 const d=preview({total_cents:22000,people:p,strategy:"equal",maximum_absent:5,max_share_cents:1200});
 assert.equal(d.mode,"BROWSER_LOCAL_FICTIONAL_DEMO");
 assert.equal(d.read_only,true);
 assert.equal(d.first_target_breach_at_absences,2);
 assert.deepEqual(d.projections.map(r=>r.largest_share_cents),[1100,1158,1223,1295,1375,1467]);
 assert.deepEqual(d.projections.map(r=>r.minimum_replacements_needed),[0,0,1,2,3,4]);
 assert.equal(JSON.stringify(p),before);
});

test("weighted member absences require replacing lost weight, not merely lost headcount",()=>{
 const d=preview({total_cents:10001,people:[
  {id:10,weight:3},{id:20,weight:2},{id:30,weight:1}
 ],strategy:"weighted",maximum_absent:2,max_share_cents:7000});
 assert.deepEqual(d.projections.map(r=>r.largest_share_cents),[5000,7501,10001]);
 assert.deepEqual(d.projections.map(r=>r.minimum_replacements_needed),[0,1,2]);
 assert.equal(d.projections[1].best_replacement_largest_share_cents,6001);
});

test("unreachable cap is explicit and respects fifty-person recovery search bound",()=>{
 const d=preview({total_cents:22000,people:people(20),
  strategy:"equal",maximum_absent:2,max_share_cents:1});
 for(const r of d.projections){
  assert.equal(r.replacements_feasible,false);
  assert.equal(r.minimum_replacements_needed,null);
  assert.equal(r.maximum_replacements_considered,50);
  assert.equal(r.replacement_candidates_tested,51);
  assert(r.replacement_gap_cents>0);
 }
});

test("one-member and full-cap events never model an empty or 201-member group",()=>{
 const one=preview({total_cents:3000,people:[{id:1,weight:1}],
  strategy:"equal",maximum_absent:20,max_share_cents:2000});
 assert.equal(one.projections.length,1);
 assert.equal(one.projections[0].minimum_replacements_needed,1);
 const full=preview({total_cents:10000,people:people(200),
  strategy:"equal",maximum_absent:1,max_share_cents:1});
 assert.equal(full.projections[0].maximum_replacements_considered,0);
 assert.equal(full.projections[1].maximum_replacements_considered,1);
});

test("untrusted browser model and unsafe money precision fail closed",()=>{
 const p=people(3);
 for(const input of [
  {total_cents:-1},{total_cents:100.2},{strategy:"live"},
  {maximum_absent:-1},{maximum_absent:21},{maximum_absent:3.5},
  {maximum_absent:true},{max_share_cents:0},{max_share_cents:10000001},
  {people:[]},{people:[{id:1,weight:0}]},
  {people:[{id:1,weight:1},{id:1,weight:1}]},
  {people:people(201)}
 ]){
  assert.throws(()=>preview({
   total_cents:10000,people:p,strategy:"equal",
   maximum_absent:2,max_share_cents:1200,...input
  }));
 }
});

test("public demo exposes an accessible distinct local planning view",()=>{
 assert.match(html,/data-view="resilience"/);
 assert.match(html,/id="resilience" class="panel"/);
 assert.match(html,/id="recovery-form"/);
 assert.match(html,/id="recovery-results" role="status" aria-live="polite"/);
 assert.match(html,/script src="\/static\/public_recovery\.js"/);
 assert.match(html,/Browser-only preview/);
 assert.match(html,/one adverse illustration, not a worst-case guarantee/);
 assert.match(html,/These hypothetical additions are not RSVPs, consent or payments/);
});

function browser(){
 const elements=new Map();
 let storageWrites=0, fetchCalls=0;
 function el(id){
  if(!elements.has(id)){
   const obj={id,handlers:{},style:{},className:"",disabled:false,
    value:({recoveryCap:"12.00",recoveryAbsent:"5",recoveryStrategy:"equal"})[id]??"",
    innerHTML:"",textContent:"",dataset:{},
    addEventListener(name,fn){this.handlers[name]=fn;},
    classList:{add(){},remove(){},toggle(){}},
    reset(){}};
   elements.set(id,obj);
  }
  return elements.get(id);
 }
 const doc={
  getElementById:el,
  querySelectorAll(){return []},
  addEventListener(){}
 };
 const context=vm.createContext({
  document:doc,window:{CircleSplitPublicRecovery:{preview},scrollTo(){}},
  localStorage:{getItem(){return null},setItem(){storageWrites++}},
  fetch(){fetchCalls++;throw Error("Public preview must not call network")},
  Date,Math,Number,JSON,Error,String,Set,Array,confirm(){return false}
 });
 const source=html.match(/<script>([\s\S]*?)<\/script>/)?.[1];
 assert(source,"Public demo inline script not found");
 vm.runInContext(source,context,{timeout:3000});
 return {el,context,get writes(){return storageWrites},get fetches(){return fetchCalls}};
}

test("real browser form runs read-only preview without API calls or local storage writes",()=>{
 const h=browser();
 const before=vm.runInContext("JSON.stringify(model)",h.context);
 h.el("recovery-form").handlers.submit({preventDefault(){}});
 const shown=h.el("recovery-results").innerHTML;
 assert.match(shown,/At 2 modeled no-show/);
 assert.match(shown,/1 extra fictional attendee/);
 assert.match(shown,/\$12\.23/);
 assert.match(shown,/No event data was changed/);
 assert.equal(vm.runInContext("JSON.stringify(model)",h.context),before);
 assert.equal(h.writes,0);
 assert.equal(h.fetches,0);
});

test("local preview rejects empty events and clears obsolete calculations when inputs change",()=>{
 const h=browser();
 h.el("recovery-form").handlers.submit({preventDefault(){}});
 assert.match(h.el("recovery-results").innerHTML,/Recovery attendees/);
 h.el("recoveryCap").handlers.input();
 assert.match(h.el("recovery-results").textContent,/Choose your target/);
 h.el("recoveryAbsent").value="-2";
 h.el("recovery-form").handlers.submit({preventDefault(){}});
 assert.match(h.el("recovery-results").textContent,/No-shows must be an integer/);
 assert.equal(h.fetches,0);
});

test("malformed attendee records are rejected before sorting and never mutate inputs",()=>{
 const valid=[{id:2,weight:2},{id:1,weight:1}];
 const before=JSON.stringify(valid);
 assert.deepEqual(exactSplit(101,valid,"weighted"),[34,67]);
 assert.equal(JSON.stringify(valid),before);
 for(const bad of [null,undefined,false,42,"person",[],{id:1,weight:1.5},
  {id:0,weight:1},{id:Number.MAX_SAFE_INTEGER+1,weight:1}]){
  assert.throws(()=>exactSplit(101,[{id:2,weight:1},bad],"weighted"),
   /Invalid fictional attendees/);
 }
});

test("deterministic varied cent allocations conserve every cent and are order-independent",()=>{
 let seed=0x5eed1234;
 const random=()=>{seed=(Math.imul(seed,1664525)+1013904223)>>>0;return seed;};
 for(let iteration=0;iteration<500;iteration++){
  const count=1+random()%40;
  const members=Array.from({length:count},(_,id)=>({
   id:id+1,weight:1+random()%10
  }));
  const total=random()%10000001;
  const strategy=random()%2?"equal":"weighted";
  const original=JSON.stringify(members);
  const shares=exactSplit(total,members,strategy);
  const backwards=exactSplit(total,[...members].reverse(),strategy);
  assert.deepEqual(shares,backwards,"input order must not change ID-sorted allocations");
  assert.equal(shares.length,count);
  assert(shares.every(cents=>Number.isSafeInteger(cents)&&cents>=0));
  assert.equal(shares.reduce((sum,cents)=>sum+cents,0),total);
  assert.equal(JSON.stringify(members),original,"the computation must be read-only");
 }
});
