"use strict";
function pulseDate(value,today){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(String(value)))return "unknown";
 const [y,m,d]=value.split("-").map(Number),dt=new Date(Date.UTC(y,m-1,d));
 if(dt.getUTCFullYear()!==y||dt.getUTCMonth()+1!==m||dt.getUTCDate()!==d)return "unknown";
 return value<today?"past":value===today?"today":(dt.getTime()-Date.parse(today+"T00:00:00Z"))/86400000<=7?"soon":"future";
}
function pulseLocalDay(date=new Date()){return [date.getFullYear(),String(date.getMonth()+1).padStart(2,"0"),String(date.getDate()).padStart(2,"0")].join("-");}
const ranks={blocker:0,attention:1,planning:2};
function pulseEvent(e,orders=[],today="2026-11-03"){
 const people=Array.isArray(e.people)?e.people:[],tasks=Array.isArray(e.tasks)?e.tasks:[],
 budget=Number(e.total_cents)||0,verified=Number(e.sandbox_cents)||0;
 const approval=people.filter(p=>p.status==="unpaid"&&!p.approved&&Number(p.share_cents)>0).length;
 const openOrders=orders.filter(p=>p.event_id===e.id&&p.status!=="completed").length;
 const completed=tasks.filter(t=>!!t.completed).length,actions=[];
 function add(code,level,title,detail,tab){actions.push({code,level,title,detail,tab,eventId:e.id,eventName:e.name,date:e.date});}
 if(!people.length)add("people","blocker","Add participants","No assigned contributions yet.","events");
 if(budget<=0)add("budget","blocker","Add expenses","The planned budget is empty.","events");
 if(people.length&&people.reduce((n,p)=>n+(Number(p.share_cents)||0),0)!==budget)
  add("allocation","blocker","Review allocation","Allocated shares do not equal the budget.","events");
 if(openOrders)add("orders","blocker","Reconcile PayPal orders",openOrders+" sandbox order(s) not recorded as captured.","activity");
 if(approval)add("approval","attention","Request approvals",approval+" fictional share(s) awaiting approval.","contributions");
 if(!tasks.length)add("checklist","planning","Plan the event","Create a preparation checklist.","events");
 else if(completed<tasks.length)add("tasks","planning","Finish preparation",(tasks.length-completed)+" preparation task(s) remaining.","events");
 const dateState=pulseDate(e.date,today);
 if(dateState==="past"&&budget>verified)add("past","planning","Review past event","Past date with unconfirmed sandbox contributions; not a real debt.","insights");
 if(dateState==="unknown")add("date","attention","Check event date","Invalid or unknown event date.","events");
 const blockers=actions.filter(a=>a.level==="blocker").length,attention=actions.filter(a=>a.level==="attention").length;
 return {id:e.id,name:e.name,date:e.date,actions,blockers,attention,approval,openOrders,
  tasksTotal:tasks.length,tasksDone:completed,budget,verified,simulated:Number(e.simulated_cents)||0,
  outstanding:Math.max(0,budget-verified),people:people.length,
  status:blockers?"Needs setup":attention?"Needs approval":"Planning progressing"};
}
function pulseSummary(events=[],orders=[],today="2026-11-03"){
 const items=events.map(e=>pulseEvent(e,orders,today));
 const actions=items.flatMap(e=>e.actions).sort((a,b)=>ranks[a.level]-ranks[b.level]||
  String(a.date).localeCompare(String(b.date))||Number(a.eventId)-Number(b.eventId));
 return {items,actions,setup:items.filter(x=>x.blockers>0).length,
  approvals:items.filter(x=>!x.blockers&&x.attention>0).length,
  orders:items.reduce((n,x)=>n+x.openOrders,0),
  progressing:items.filter(x=>!x.blockers&&!x.attention).length};
}
function pulseBriefing(e){
 const p=pulseEvent(e,[]);
 return "CircleSplit AI — SANDBOX EVENT BRIEF\nEvent: "+p.name+"\nDate: "+p.date+
 "\nPlanned budget: "+(p.budget/100).toFixed(2)+" USD\nParticipants: "+p.people+
 "\nAwaiting approval: "+p.approval+"\nPreparation: "+p.tasksDone+"/"+p.tasksTotal+
 "\nVerified PayPal sandbox captures: "+(p.verified/100).toFixed(2)+" USD"+
 "\nUnconfirmed sandbox amount: "+(p.outstanding/100).toFixed(2)+" USD"+
 "\nSimulated contributions excluded. Fictional hackathon data only. NOT an invoice or real debt.";
}
if(typeof module!=="undefined"&&module.exports)module.exports={pulseDate,pulseLocalDay,pulseEvent,pulseSummary,pulseBriefing};