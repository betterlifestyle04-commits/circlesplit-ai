"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const api=require("../static/public_portability.js");

const html=fs.readFileSync(path.join(__dirname,"../static/public.html"),"utf8");
const DATE="2026-11-06T01:00:00.000Z";
function seed(){
 return {next:100,events:[{
  id:1,name:"Friday Volleyball",date:"2026-11-06",strategy:"equal",
  expenses:[{id:2,title:"Court",cents:100},{id:3,title:"Snacks",cents:1}],
  people:[
   {id:12,name:"Sam",weight:1,share_cents:33,approved:false,status:"unpaid"},
   {id:10,name:"Alex",weight:2,share_cents:34,approved:true,status:"demo_paid"},
   {id:11,name:"Taylor",weight:1,share_cents:34,approved:true,status:"unpaid"}
  ]
 }]};
}
function envelope(){return api.exportSnapshot(seed(),DATE)}
function modify(fn){const v=seed();fn(v);return v}
function restore(model){return api.importSnapshot(JSON.stringify(api.exportSnapshot(model,DATE)))}

test("public demo validates its persisted model and clones only allowed fields",()=>{
 const original=seed(),normalized=api.validateModel(original);
 assert.deepEqual(normalized,original);
 assert.notEqual(normalized,original);
 assert.notEqual(normalized.events[0],original.events[0]);
 normalized.events[0].name="Changed";
 assert.equal(original.events[0].name,"Friday Volleyball");
});

test("versioned JSON is fully local and round-trips simulated contributions",()=>{
 const saved=envelope();
 assert.equal(saved.kind,"circlesplit-public-demo-planning");
 assert.equal(saved.schema_version,1);
 assert.equal(saved.mode,"BROWSER_LOCAL_FICTIONAL_DEMO");
 assert.equal(saved.contains_real_payments,false);
 assert.equal(saved.contains_provider_credentials,false);
 assert.equal(saved.event_count,1);
 assert.equal(saved.participant_count,3);
 assert.equal(saved.expense_count,2);
 const result=api.importSnapshot(JSON.stringify(saved));
 assert.deepEqual(result.model,seed());
 assert.deepEqual(result.summary,{
  events:1,participants:3,expenses:2,simulated:1
 });
 assert.deepEqual(api.validateModel(result.model),result.model);
});

test("equal-share and weighted-share exact-cent rounding reject forged totals",()=>{
 const data=seed();
 data.events[0].people[0].share_cents+=1;
 assert.throws(()=>api.validateModel(data),/exact-cent budget allocation/);
 const weighted=modify(v=>{
  v.events[0].strategy="weighted";
  v.events[0].people[0].share_cents=25;
  v.events[0].people[1].share_cents=51;
  v.events[0].people[2].share_cents=25;
 });
 assert.deepEqual(restore(weighted).model,weighted);
 weighted.events[0].people[1].share_cents=50;
 assert.throws(()=>api.validateModel(weighted),/exact-cent budget allocation/);
});

test("import rejects malformed JSON, oversize files and mismatched count claims",()=>{
 for(const input of ["","{","null","[]","{\"events\":[]}","x".repeat(api.MAX_BYTES+1)])
  assert.throws(()=>api.importSnapshot(input));
 for(const change of [
  o=>o.event_count=100,
  o=>o.participant_count=4,
  o=>o.expense_count=10,
  o=>o.mode="LIVE",
  o=>o.kind="circlesplit-private-reconciliation",
  o=>o.contains_real_payments=true,
  o=>o.contains_provider_credentials=true,
  o=>o.schema_version=2,
  o=>o.exported_at="invalid",
  o=>o.order_id="PAYPAL-ORDER-123",
 ]){
  const snapshot=envelope();change(snapshot);
  assert.throws(()=>api.importSnapshot(JSON.stringify(snapshot)));
 }
});

test("external payment, token and webhook fields are rejected at all levels",()=>{
 for(const change of [
  x=>x.paypal_order_id="UNEXPECTED",
  x=>x.events[0].paypal_capture_id="UNEXPECTED",
  x=>x.events[0].people[0].token="PRIVATE",
  x=>x.events[0].expenses[0].capture_id="UNEXPECTED",
  x=>x.events[0].people[0].status="sandbox_paid",
  x=>x.events[0].people[0].status="approved",
 ]){
  const value=seed();change(value);
  assert.throws(()=>api.validateModel(value));
 }
});

test("duplicate or unsafe record IDs are rejected across event people and expenses",()=>{
 for(const change of [
  x=>x.events[0].people[0].id=10,
  x=>x.events[0].expenses[0].id=1,
  x=>x.events[0].people[0].id=0,
  x=>x.events[0].people[0].id="12",
  x=>x.events[0].people[0].id=Infinity,
  x=>x.next=2,
  x=>x.next=1.5,
  x=>x.events[0].id=-1,
 ]){
  const value=seed();change(value);
  assert.throws(()=>api.validateModel(value));
 }
});

test("invalid names, dates, weights and flags never normalize silently",()=>{
 for(const change of [
  x=>x.events[0].name=" ",
  x=>x.events[0].name="<".repeat(91),
  x=>x.events[0].name="Spaces ",
  x=>x.events[0].date="2026-02-30",
  x=>x.events[0].date="2026-11-06T00:00:00Z",
  x=>x.events[0].strategy="AI",
  x=>x.events[0].people[0].weight=0,
  x=>x.events[0].people[0].approved=1,
  x=>x.events[0].people[1].approved=false,
  x=>x.events[0].people[0].share_cents=-2,
  x=>x.events[0].expenses[0].cents="100",
  x=>x.events[0].expenses[0].cents=0,
  x=>x.events[0].expenses[0].cents=10000001,
  x=>x.events[0].expenses[0].title="",
  x=>x.events[0].people[0].name="Bad\nname"
 ]){
  const value=seed();change(value);
  assert.throws(()=>api.validateModel(value));
 }
});

test("empty and partially planned events can still be safely exported",()=>{
 const empty={next:1,events:[]};
 assert.deepEqual(restore(empty).model,empty);
 const noPeople={
  next:2,events:[{
   id:2,name:"New board game night",date:"2026-11-06",
   strategy:"equal",expenses:[],people:[]
  }]
 };
 assert.deepEqual(restore(noPeople).model,noPeople);
 const noExpenses={
  next:3,events:[{
   id:2,name:"New board game night",date:"2026-11-06",
   strategy:"weighted",expenses:[],people:[{
    id:3,name:"Alex",weight:1,share_cents:0,approved:false,status:"unpaid"
   }]
  }]
 };
 assert.deepEqual(restore(noExpenses).model,noExpenses);
});

test("import bounds protect the public browser from oversized datasets",()=>{
 const tooMany=modify(x=>{
  x.events=Array.from({length:26},(_,i)=>({
   id:101+i,name:"Event "+i,date:"2026-11-06",
   strategy:"equal",expenses:[],people:[]
  }));
  x.next=126;
 });
 assert.throws(()=>api.validateModel(tooMany),/too many events/);
 const manyPeople=modify(x=>{
  const ev=x.events[0];ev.expenses=[];
  ev.people=Array.from({length:201},(_,i)=>({
   id:200+i,name:"Guest "+i,weight:1,
   share_cents:0,approved:false,status:"unpaid"
  }));
  x.next=500;
 });
 assert.throws(()=>api.validateModel(manyPeople),/Too many demo expenses or participants/);
});

test("safe-looking extra JSON properties remain forbidden, including prototype keys",()=>{
 const d=seed();
 d.events[0].people[0]["__proto__"]="weird";
 // JSON.parse creates __proto__ as own enumerable data instead of a setter.
 const raw=JSON.stringify(envelope()).replace('"weight":1','"__proto__":{"admin":true},"weight":1');
 assert.throws(()=>api.importSnapshot(raw));
 assert.equal(Object.prototype.admin,undefined);
});

test("public UI provides browser-only backup controls and explicit overwrite consent",()=>{
 assert.match(html,/id="demo-backup-download"/);
 assert.match(html,/id="demo-backup-restore"/);
 assert.match(html,/id="demo-backup-file"[^>]*accept="application\/json,\.json"/);
 assert.match(html,/id="demo-backup-status"[^>]*role="status"/);
 assert.match(html,/script src="\/static\/public_portability\.js"/);
 assert.match(html,/window\.CircleSplitPublicPortability\.importSnapshot\(await file\.text\(\)\)/);
 assert.match(html,/window\.confirm\("Replace this browser's current fictional demo/);
 assert.match(html,/localStorage\.setItem\(STORAGE,JSON\.stringify\(candidate\.model\)\)/);
 assert.match(html,/No server, PayPal, Gemini or organizer records were contacted/);
 assert.match(html,/File|"demo-backup-file"|file\.size/);
});

test("public mutation helper reverts invalid edits rather than retaining partial state",()=>{
 const begin=html.indexOf("function change(fn){"),end=html.indexOf("function amount(",begin);
 assert(begin>=0&&end>begin);
 const source=html.slice(begin,end);
 const old=seed(),oldJSON=JSON.stringify(old),notices=[];
 const doc={
  recoveryStrategy:{value:"equal"},
  };
 const context=vm.createContext({
  model:old,chosen:1,
  window:{CircleSplitPublicPortability:api},
  event:()=>null,
  save:()=>true,resetRecovery:()=>{},render:()=>{},
  message:msg=>notices.push(msg),
  $:id=>doc[id],
  JSON,Error
 });
 vm.runInContext(source,context);
 const change=vm.runInContext("change",context);
 change(()=>{old.next=999;throw Error("Invalid USD amount")});
 assert.equal(JSON.stringify(context.model),oldJSON);
 assert.equal(context.chosen,1);
 assert.match(notices[0],/Invalid USD amount/);
});


function restoreHarness({backup,confirmed=true,writeError=null}={}){
 const beginning=html.indexOf('$("demo-backup-file").addEventListener("change",async function(){');
 const end=html.indexOf('$("addEvent").addEventListener',beginning);
 assert(beginning>0&&end>beginning);
 const code=html.slice(beginning,end);
 const calls=[],handlers={};
 const input={value:"initial-file-selection",addEventListener:(name,fn)=>{handlers[name]=fn}};
 const status={textContent:""};
 const strategy={value:"equal"};
 const selected={id:4};
 const initial=seed();
 const ctx=vm.createContext({
  window:{
   CircleSplitPublicPortability:api,
   confirm:(question)=>{calls.push(["confirm",question]);return confirmed;}
  },
  $:id=>({
   "demo-backup-file":input,
   "demo-backup-status":status,
   "recoveryStrategy":strategy
  })[id],
  localStorage:{
   setItem:(...values)=>{
    calls.push(["storage",...values]);
    if(writeError)throw Error(writeError);
   }
  },
  STORAGE:"circlesplit-public-demo-v1",
  model:initial,chosen:1,storageNeedsRecovery:false,
  resetRecovery:()=>calls.push(["reset-scenario"]),
  event:()=>selected,render:()=>calls.push(["render"]),
  Error,JSON
 });
 vm.runInContext(code,ctx,{timeout:2000});
 assert.equal(typeof handlers.change,"function");
 return {run:()=>handlers.change.call({
   files:backup===null?[]:[{
    size:backup?.size??new TextEncoder().encode(
     backup?.content??JSON.stringify(envelope())).length,
    text:async()=>backup?.content??JSON.stringify(envelope())
   }],
   value:"selected"
  }),ctx,status,calls,input,initial};
}

test("restore cancellation does not replace browser data or write storage",async()=>{
 const h=restoreHarness({backup:{content:JSON.stringify(envelope())},confirmed:false});
 await h.run();
 assert.equal(h.calls.filter(x=>x[0]==="storage").length,0);
 assert.deepEqual(h.ctx.model,h.initial);
 assert.equal(h.ctx.chosen,1);
 assert.match(h.status.textContent,/Restore cancelled/);
});

test("invalid restore is rejected before showing an overwrite confirmation",async()=>{
 const bad=envelope();
 bad.data.events[0].people[0].share_cents=999;
 const h=restoreHarness({backup:{content:JSON.stringify(bad)}});
 await h.run();
 assert.equal(h.calls.filter(x=>x[0]==="confirm").length,0);
 assert.equal(h.calls.filter(x=>x[0]==="storage").length,0);
 assert.deepEqual(h.ctx.model,h.initial);
 assert.match(h.status.textContent,/Restore rejected/);
});

test("successful restore persists a validated data-only plan before changing memory",async()=>{
 const altered=seed();
 altered.events[0].name="Saved planning copy";
 const h=restoreHarness({backup:{
  content:JSON.stringify(api.exportSnapshot(altered,DATE))
 }});
 await h.run();
 assert.equal(h.calls.filter(x=>x[0]==="storage").length,1);
 assert.equal(h.calls.filter(x=>x[0]==="confirm").length,1);
 assert.deepEqual(h.ctx.model,altered);
 assert.deepEqual(JSON.parse(h.calls.find(x=>x[0]==="storage")[2]),altered);
 assert.equal(h.ctx.storageNeedsRecovery,false);
 assert.match(h.status.textContent,/No server, PayPal, Gemini or organizer/);
});

test("storage write failure never overwrites in-memory demo",async()=>{
 const altered=seed();altered.events[0].name="Another plan";
 const h=restoreHarness({backup:{
  content:JSON.stringify(api.exportSnapshot(altered,DATE))
 },writeError:"Storage disabled"});
 await h.run();
 assert.equal(h.calls.filter(x=>x[0]==="storage").length,1);
 assert.deepEqual(h.ctx.model,h.initial);
 assert.match(h.status.textContent,/current demo unchanged/);
});
