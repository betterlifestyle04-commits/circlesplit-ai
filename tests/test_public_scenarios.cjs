"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const portable=require("../static/public_portability.js");
const recovery=require("../static/public_recovery.js");
const drafts=require("../static/public_scenarios.js");
const html=fs.readFileSync(path.join(__dirname,"../static/public.html"),"utf8");

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
const json=value=>JSON.stringify(value);

test("what-if copy uses fresh IDs, exact cents and never carries simulated payment or consent",()=>{
 const source=sample(),before=json(source);
 const cloned=drafts.duplicateAsDraft(source,1,portable);
 assert.equal(json(source),before,"The original model must stay unchanged");
 assert.notEqual(cloned.model,source);
 assert.deepEqual(cloned.summary,{
  sourceEventId:1,newEventId:101,budget_cents:101,participants:3,
  expenses:2,approvals_copied:0,payments_copied:0,
  mode:"BROWSER_LOCAL_FICTIONAL_DRAFT"
 });
 const copied=cloned.model.events[0];
 const original=cloned.model.events[1];
 assert.equal(copied.name,"Fictional volleyball (what-if draft)");
 assert.equal(copied.id,101);
 assert.equal(copied.date,original.date);
 assert.equal(copied.strategy,original.strategy);
 assert.deepEqual(copied.expenses.map(x=>x.id),[102,103]);
 assert.deepEqual(copied.people.map(x=>x.id),[104,105,106]);
 assert.deepEqual(copied.people.map(x=>x.name),["Sam","Alex","Taylor"]);
 assert.deepEqual(copied.people.map(x=>x.share_cents),[34,34,33]);
 assert(copied.people.every(p=>p.status==="unpaid"&&p.approved===false));
 assert.equal(original.people[1].status,"demo_paid");
 assert.equal(original.people[0].approved,true);
 assert.equal(cloned.model.next,106);
 assert.deepEqual(portable.validateModel(cloned.model),cloned.model);
 assert.equal(cloned.model.events.reduce((n,e)=>n+e.people.filter(p=>p.status==="demo_paid").length,0),1);
});

test("what-if copy recalculates weighted shares using NEW deterministic ID order",()=>{
 const original=sample();
 original.events[0].strategy="weighted";
 // Original ID order: Alex (2), Taylor (1), Sam (1)
 // 101 cents => Alex 51, Taylor 25, Sam 25.
 original.events[0].people[0].share_cents=25;
 original.events[0].people[1].share_cents=51;
 original.events[0].people[2].share_cents=25;
 const copy=drafts.duplicateAsDraft(original,1,portable).model.events[0];
 // Copy ID order: Sam (1), Alex (2), Taylor (1)
 // New tied rounding is allocated to Alex first, then Sam or Taylor.
 assert.deepEqual(copy.people.map(x=>x.share_cents),[25,51,25]);
 assert.equal(copy.people.reduce((sum,p)=>sum+p.share_cents,0),101);
 assert.equal(copy.strategy,"weighted");
 assert(copy.people.every(x=>!x.approved&&x.status==="unpaid"));
});

test("scenario cloning supports blank-event drafts and does not invent any payment",()=>{
 const empty={next:1,events:[{
  id:1,name:"New fictional night",date:"2026-11-06",
  strategy:"equal",expenses:[],people:[]
 }]};
 const next=drafts.duplicateAsDraft(empty,1,portable);
 assert.equal(next.model.events[0].expenses.length,0);
 assert.equal(next.model.events[0].people.length,0);
 assert.equal(next.model.events[0].id,2);
 assert.equal(next.model.next,2);
 assert.deepEqual(portable.validateModel(next.model),next.model);
});

test("repeated what-if copies remain independent and keep all IDs globally unique",()=>{
 let data=sample();
 for(let i=0;i<4;i++){
  data=drafts.duplicateAsDraft(data,data.events[0].id,portable).model;
 }
 const ids=[];
 for(const e of data.events){
  ids.push(e.id);
  ids.push(...e.expenses.map(x=>x.id));
  ids.push(...e.people.map(x=>x.id));
 }
 assert.equal(new Set(ids).size,ids.length);
 assert.equal(data.events.length,5);
 assert.equal(data.events.filter(x=>x.people.some(p=>p.status==="demo_paid")).length,1);
 assert.equal(data.events[0].people.every(p=>p.status==="unpaid"),true);
 assert.deepEqual(portable.validateModel(data),data);
});

test("invalid source, maximum event count, and exhausted IDs fail without mutation",()=>{
 const source=sample(),before=json(source);
 assert.throws(()=>drafts.duplicateAsDraft(source,999,portable),/Select an existing/);
 assert.throws(()=>drafts.duplicateAsDraft(source,1,null),/validator unavailable/);
 assert.throws(()=>drafts.duplicateAsDraft(source,1,{
  validateModel:()=>{throw Error("Malformed browser state")}
 }),/Malformed browser state/);
 assert.equal(json(source),before);
 const full={next:1000,events:Array.from({length:25},(_,i)=>({
  id:201+i,name:"Event "+i,date:"2026-11-06",
  strategy:"equal",expenses:[],people:[]
 }))};
 assert.throws(()=>drafts.duplicateAsDraft(full,201,portable),/Maximum 25/);
 assert.deepEqual(portable.validateModel(full),full);
 const exhausted=sample();exhausted.next=1000000000000;
 assert.throws(()=>drafts.duplicateAsDraft(exhausted,1,portable),/No more safe/);
 assert.equal(json(source),before);
});

test("copied drafts respect total participant and expense limits",()=>{
 const data={
  next:20000,events:Array.from({length:6},(_,i)=>({
   id:100+i,name:"Fictional group "+i,date:"2026-11-06",
   strategy:"equal",
   expenses:Array.from({length:80},(_,j)=>({
    id:1000+i*100+j,title:"Budget item "+j,cents:100
   })),
   people:Array.from({length:165},(_,j)=>({
    id:3000+i*200+j,name:"Member "+j,weight:1,
    share_cents:j<80?49:48,approved:false,status:"unpaid"
   }))
  }))
 };
 // 80 expenses × 100 cents = 8000; 165 participants get 49 × 80,
 // and 48 × 85, for exact cents across a fully valid 990-person fixture.
 assert.deepEqual(portable.validateModel(data),data);
 assert.throws(()=>drafts.duplicateAsDraft(data,100,portable),/1,000-person/);
 const expenseData={next:20000,events:Array.from({length:5},(_,i)=>({
  id:100+i,name:"Fictional expenses "+i,date:"2026-11-06",
  strategy:"equal",
  expenses:Array.from({length:100},(_,j)=>({
   id:1000+i*100+j,title:"Expense "+j,cents:10
  })),people:[]
 }))};
 assert.deepEqual(portable.validateModel(expenseData),expenseData);
 assert.throws(()=>drafts.duplicateAsDraft(expenseData,100,portable),/500-expense/);
});

test("public page explicitly exposes an editable what-if action and safe browser module",()=>{
 assert.match(html,/id="duplicate-event"/);
 assert.match(html,/Duplicate as what-if draft/);
 assert.match(html,/script src="\/static\/public_scenarios\.js"/);
 assert.match(html,/window\.CircleSplitPublicScenarios\.duplicateAsDraft/);
 assert.match(html,/Original approvals and simulated contributions were not copied/);
 assert.match(html,/No PayPal request was made/);
});

function launchPublic(){
 const script=html.match(/<script>([\s\S]*?)<\/script>/g);
 assert.equal(script.length,1);
 const inner=script[0].slice("<script>".length,-"</script>".length);
 const handlers=new Map(),elements=new Map(),stored=new Map(),network=[];
 class Element {
  constructor(id){
   this.id=id;this.value="";
   this.textContent="";this.innerHTML="";
   this.disabled=false;this.style={};
   this.className="";
   this.classList={add(){},remove(){},toggle(){}};
   this.dataset={};
  }
  addEventListener(kind,callback){
   handlers.set(this.id+":"+kind,callback);
  }
  reset(){}
 }
 function el(id){
  if(!elements.has(id))elements.set(id,new Element(id));
  return elements.get(id);
 }
 const document={
  getElementById:el,
  querySelectorAll:()=>[],
  addEventListener:(name,fn)=>handlers.set("document:"+name,fn)
 };
 const context=vm.createContext({
  document,
  window:{
   CircleSplitPublicRecovery:recovery,
   CircleSplitPublicPortability:portable,
   CircleSplitPublicScenarios:drafts,
   scrollTo:()=>{}
  },
  localStorage:{
   getItem:k=>stored.get(k)??null,
   setItem:(k,v)=>stored.set(k,v)
  },
  confirm:()=>true,
  URL,Blob,Error,Date,JSON,Number,
  fetch:(...args)=>{network.push(args);throw Error("No network from public demo")}
 });
 vm.runInContext(inner,context,{timeout:2500});
 function trigger(id,kind,evt={preventDefault(){}}){
  const fn=handlers.get(id+":"+kind);
  assert.equal(typeof fn,"function",id+":"+kind);
  return fn(evt);
 }
 return {context,el,trigger,stored,network,handlers,
  getModel:()=>vm.runInContext("model",context),
  getChosen:()=>vm.runInContext("chosen",context)};
}

test("real public inline JS initializes sample events and remains browser-only",()=>{
 const ui=launchPublic();
 assert.equal(ui.el("kEvents").textContent,1);
 assert.equal(ui.el("kBudget").textContent,"$220.00");
 assert.equal(ui.el("kPeople").textContent,20);
 assert.equal(ui.el("kPaid").textContent,"$0.00");
 assert.equal(ui.el("duplicate-event").disabled,false);
 assert.match(ui.el("eventSummary").innerHTML,/Friday Community Volleyball/);
 assert.equal(ui.network.length,0);
});

test("browser simulation locks ORIGINAL event; what-if button creates separate editable plan",()=>{
 const ui=launchPublic();
 const original=ui.getModel().events[0];
 const originalId=original.people[0].id;
 const click=(dataset)=>{
  const fn=ui.handlers.get("document:click");
  fn({target:{closest:()=>({dataset})}});
 };
 click({approve:String(originalId)});
 assert.equal(ui.getModel().events[0].people[0].approved,true);
 click({simulate:String(originalId)});
 assert.equal(ui.getModel().events[0].people[0].status,"demo_paid");
 assert.equal(ui.el("equal").disabled,true);
 assert.equal(ui.el("kPaid").textContent,"$11.00");
 ui.trigger("duplicate-event","click");
 const copied=ui.getModel().events[0],old=ui.getModel().events[1];
 assert.equal(ui.getChosen(),copied.id);
 assert.notEqual(copied.id,old.id);
 assert.equal(ui.el("kEvents").textContent,2);
 assert.equal(ui.el("kBudget").textContent,"$440.00");
 assert.equal(ui.el("kPaid").textContent,"$11.00");
 assert.equal(ui.el("equal").disabled,false);
 assert(copied.people.every(p=>p.approved===false&&p.status==="unpaid"));
 assert.equal(old.people[0].status,"demo_paid");
 assert.match(ui.el("message").textContent,/No PayPal request was made/);
 assert.deepEqual(portable.validateModel(ui.getModel()),ui.getModel());
 ui.trigger("weighted","click");
 assert.equal(ui.getModel().events[0].strategy,"weighted");
 assert.equal(ui.getModel().events[1].strategy,"equal");
 assert.equal(ui.getModel().events[0].people.reduce((s,p)=>s+p.share_cents,0),22000);
 assert.equal(ui.network.length,0);
});

test("public resilience lab calculates an exact-cent absence scenario without requests",()=>{
 const ui=launchPublic();
 ui.el("recoveryCap").value="12.00";
 ui.el("recoveryAbsent").value="2";
 ui.el("recoveryStrategy").value="equal";
 ui.trigger("recovery-form","submit");
 assert.match(ui.el("recovery-results").innerHTML,/1 extra fictional attendee/);
 assert.match(ui.el("recovery-results").innerHTML,/No event data was changed/);
 assert.equal(ui.el("kPaid").textContent,"$0.00");
 assert.equal(ui.network.length,0);
});


test("real browser-local event planner shows scenario comparison only with two events",()=>{
 const ui=launchPublic();
 assert.match(ui.el("compare-status").textContent,/Duplicate an event/);
 assert.equal(ui.el("cmp-budget-before").textContent,"—");
 assert.equal(ui.el("cmp-highest-delta").textContent,"—");
 ui.trigger("duplicate-event","click");
 const draft=ui.getModel().events[0],baseline=ui.getModel().events[1];
 assert.equal(ui.el("compare-baseline").value,String(baseline.id));
 assert.equal(ui.el("compare-alternative").value,String(draft.id));
 assert.match(ui.el("compare-status").textContent,/Comparing Friday Community Volleyball/);
 assert.match(ui.el("compare-status").textContent,/All amounts are fictional USD/);
 assert.equal(ui.el("cmp-budget-before").textContent,"$220.00");
 assert.equal(ui.el("cmp-budget-after").textContent,"$220.00");
 assert.equal(ui.el("cmp-budget-delta").textContent,"$0.00");
 assert.equal(ui.el("cmp-people-before").textContent,"20");
 assert.equal(ui.el("cmp-people-after").textContent,"20");
 assert.equal(ui.el("cmp-highest-delta").textContent,"$0.00");
 assert.equal(ui.el("cmp-simulated-delta").textContent,"0");
 assert.equal(ui.network.length,0);
});

test("what-if comparison updates after weighted draft change without modifying original",()=>{
 const ui=launchPublic();
 ui.trigger("duplicate-event","click");
 const original=ui.getModel().events[1],originalBudget=JSON.stringify(original);
 ui.trigger("weighted","click");
 assert.equal(ui.el("cmp-budget-delta").textContent,"$0.00");
 assert.equal(ui.el("cmp-highest-before").textContent,"$11.00");
 assert.equal(ui.el("cmp-highest-after").textContent,"$18.33");
 assert.equal(ui.el("cmp-highest-delta").textContent,"+$7.33");
 assert.equal(ui.el("cmp-lowest-after").textContent,"$9.16");
 assert.equal(ui.el("cmp-lowest-delta").textContent,"−$1.84");
 assert.equal(JSON.stringify(ui.getModel().events[1]),originalBudget);
 assert.equal(ui.network.length,0);
});

test("comparison dropdown changes never trigger payments or mutate simulated states",()=>{
 const ui=launchPublic();
 ui.trigger("duplicate-event","click");
 const draftId=ui.getModel().events[0].id;
 const sourceId=ui.getModel().events[1].id;
 const before=JSON.stringify(ui.getModel());
 ui.trigger("compare-baseline","change",{target:{value:String(draftId)}});
 assert.match(ui.el("compare-status").textContent,/Choose two different/);
 assert.equal(ui.el("cmp-budget-before").textContent,"—");
 ui.trigger("compare-baseline","change",{target:{value:String(sourceId)}});
 assert.match(ui.el("compare-status").textContent,/Comparing/);
 ui.trigger("compare-alternative","change",{target:{value:String(sourceId)}});
 assert.match(ui.el("compare-status").textContent,/Choose two different/);
 ui.trigger("compare-alternative","change",{target:{value:String(draftId)}});
 assert.equal(ui.el("cmp-budget-before").textContent,"$220.00");
 assert.equal(JSON.stringify(ui.getModel()),before);
 assert.equal(ui.network.length,0);
});

test("untrusted fictional event names are escaped in dropdowns and rendered as text only",()=>{
 const ui=launchPublic();
 ui.trigger("duplicate-event","click");
 ui.getModel().events[1].name="<img src=x onerror=alert(1)>";
 vm.runInContext("render()",ui.context,{timeout:2000});
 assert.match(ui.el("compare-baseline").innerHTML,/&lt;img/);
 assert.match(ui.el("compare-status").textContent,/<img src=x/);
 assert(!ui.el("compare-baseline").innerHTML.includes("<img src"));
 assert.equal(ui.network.length,0);
});
