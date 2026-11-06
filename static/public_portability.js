"use strict";
/* Portable fictional group-planning state. No network, provider tokens or payments.
   Keep validation strict so external JSON cannot corrupt the browser demo. */
(function(root){
 const TYPE="circlesplit-public-demo-planning";
 const VERSION=1;
 const MODE="BROWSER_LOCAL_FICTIONAL_DEMO";
 const MAX_BYTES=256*1024;
 const MAX_EVENTS=25, MAX_PEOPLE=1000, MAX_EXPENSES=500;
 const object=v=>v!==null&&typeof v==="object"&&!Array.isArray(v);
 const integer=(v,min,max=Number.MAX_SAFE_INTEGER)=>
  Number.isSafeInteger(v)&&v>=min&&v<=max;
 function fields(value,names,label){
  if(!object(value)||Object.keys(value).sort().join("|")!==[...names].sort().join("|"))
   throw Error(label+" has unexpected or missing fields");
 }
 function text(value,min,max,label){
  if(typeof value!=="string"||value!==value.trim()||
      value.length<min||value.length>max||/[\u0000-\u001f\u007f]/.test(value))
   throw Error("Invalid "+label);
  return value;
 }
 function calendar(value){
  if(typeof value!=="string"||!/[0-9]{4}-[0-9]{2}-[0-9]{2}/.test(value)||
      value<"1900-01-01"||value>"9999-12-31")
   throw Error("Invalid event date");
  const time=new Date(value+"T00:00:00Z");
  if(!Number.isFinite(time.getTime())||time.toISOString().slice(0,10)!==value)
   throw Error("Invalid calendar date");
  return value;
 }
 function shares(total,people,strategy){
  if(!people.length)return [];
  const weights=people.map(p=>strategy==="weighted"?p.weight:1);
  const denominator=weights.reduce((a,b)=>a+b,0);
  const allocated=weights.map(w=>Math.floor(total*w/denominator));
  const remaining=total-allocated.reduce((a,b)=>a+b,0);
  const rank=weights.map((weight,i)=>({
   i,remainder:(total*weight)%denominator,id:people[i].id
  })).sort((a,b)=>b.remainder-a.remainder||a.id-b.id);
  for(let i=0;i<remaining;i++)allocated[rank[i].i]++;
  return allocated;
 }
 function validateModel(value){
  fields(value,["next","events"],"Demo dataset");
  if(!integer(value.next,1,1000000000000)||
     !Array.isArray(value.events)||value.events.length>MAX_EVENTS)
   throw Error("Demo contains too many events or an invalid next ID");
  const known=new Set();
  let maximum=0,peopleCount=0,expenseCount=0;
  function addId(id){
   if(!integer(id,1,1000000000000)||known.has(id))
    throw Error("Invalid or repeated demo record ID");
   known.add(id);maximum=Math.max(maximum,id);
  }
  const events=value.events.map(event=>{
   fields(event,["id","name","date","strategy","expenses","people"],"Event");
   addId(event.id);
   const name=text(event.name,3,90,"event name");
   const date=calendar(event.date);
   if(event.strategy!=="equal"&&event.strategy!=="weighted")
    throw Error("Invalid allocation method");
   if(!Array.isArray(event.expenses)||event.expenses.length>200||
      !Array.isArray(event.people)||event.people.length>200)
    throw Error("Too many demo expenses or participants");
   expenseCount+=event.expenses.length;peopleCount+=event.people.length;
   if(expenseCount>MAX_EXPENSES||peopleCount>MAX_PEOPLE)
    throw Error("Demo dataset exceeds the safe import limit");
   let budget=0;
   const expenses=event.expenses.map(expense=>{
    fields(expense,["id","title","cents"],"Expense");
    addId(expense.id);
    budget+=expense.cents;
    if(!integer(expense.cents,1,10000000))
     throw Error("Invalid fictional expense amount");
    return {id:expense.id,title:text(expense.title,2,120,"expense title"),
            cents:expense.cents};
   });
   if(!Number.isSafeInteger(budget))
    throw Error("Demo budget is outside safe numeric limits");
   const people=event.people.map(person=>{
    fields(person,["id","name","weight","share_cents","approved","status"],"Participant");
    addId(person.id);
    if(!integer(person.weight,1,10)||
       !integer(person.share_cents,0,budget)||
       typeof person.approved!=="boolean"||
       !["unpaid","demo_paid"].includes(person.status))
     throw Error("Invalid fictional participant state");
    if(person.status==="demo_paid"&&(!person.approved||person.share_cents===0))
     throw Error("Simulated contribution requires approval and positive share");
    return {
     id:person.id,name:text(person.name,2,60,"participant name"),
     weight:person.weight,share_cents:person.share_cents,
     approved:person.approved,status:person.status
    };
   });
   // Public demo uses deterministic ID-sorted integer-cent allocations.
   // Reject edited shares or mismatched totals rather than normalizing
   // financial-looking values or silently adding fictional payments.
   const sorted=[...people].sort((a,b)=>a.id-b.id);
   const expected=shares(budget,sorted,event.strategy);
   for(let i=0;i<sorted.length;i++)
    if(sorted[i].share_cents!==expected[i])
     throw Error("Imported shares do not match the exact-cent budget allocation");
   return {id:event.id,name,date,strategy:event.strategy,expenses,people};
  });
  if(value.next<maximum)throw Error("Next ID conflicts with an existing record");
  return {next:value.next,events};
 }
 function exportSnapshot(model,createdAt){
  const clean=validateModel(model);
  if(typeof createdAt!=="string"||!Number.isFinite(Date.parse(createdAt))||
     new Date(createdAt).toISOString()!==createdAt)
   throw Error("Invalid export date");
  return {
   kind:TYPE,schema_version:VERSION,mode:MODE,
   contains_real_payments:false,contains_provider_credentials:false,
   exported_at:createdAt,event_count:clean.events.length,
   participant_count:clean.events.reduce((s,e)=>s+e.people.length,0),
   expense_count:clean.events.reduce((s,e)=>s+e.expenses.length,0),
   data:clean
  };
 }
 function importSnapshot(source){
  if(typeof source!=="string"||!source||source.length>MAX_BYTES)
   throw Error("The JSON backup must be no larger than 256 KiB");
  let result;
  try{result=JSON.parse(source)}
  catch(_){throw Error("Invalid demo JSON backup");}
  fields(result,[
   "kind","schema_version","mode","contains_real_payments",
   "contains_provider_credentials","exported_at","event_count",
   "participant_count","expense_count","data"
  ],"Backup envelope");
  if(result.kind!==TYPE||result.schema_version!==VERSION||
     result.mode!==MODE||result.contains_real_payments!==false||
     result.contains_provider_credentials!==false)
   throw Error("This file is not a supported browser-only fictional demo backup");
  if(typeof result.exported_at!=="string"||
     !Number.isFinite(Date.parse(result.exported_at))||
     new Date(result.exported_at).toISOString()!==result.exported_at)
   throw Error("Invalid backup timestamp");
  const clean=validateModel(result.data);
  const participants=clean.events.reduce((s,e)=>s+e.people.length,0);
  const expenses=clean.events.reduce((s,e)=>s+e.expenses.length,0);
  if(result.event_count!==clean.events.length||
     result.participant_count!==participants||
     result.expense_count!==expenses)
   throw Error("Backup event, expense or participant totals do not match");
  return {model:clean,summary:{
   events:clean.events.length,participants,expenses,
   simulated:clean.events.reduce((sum,e)=>sum+e.people
    .filter(p=>p.status==="demo_paid").length,0)
  }};
 }
 const api={validateModel,exportSnapshot,importSnapshot,MAX_BYTES};
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 else root.CircleSplitPublicPortability=api;
})(typeof window!=="undefined"?window:{});
