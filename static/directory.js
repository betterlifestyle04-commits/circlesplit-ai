"use strict";
/* Read-only event directory and exact-cent split explainability. */
function validDay(day){
 const s=String(day||"");
 if(!/^\d{4}-\d{2}-\d{2}$/.test(s))return false;
 const [y,m,d]=s.split("-").map(Number),date=new Date(Date.UTC(y,m-1,d));
 return date.getUTCFullYear()===y&&date.getUTCMonth()===m-1&&date.getUTCDate()===d;
}
function localDay(date=new Date()){
 return date.getFullYear()+"-"+String(date.getMonth()+1).padStart(2,"0")+"-"+String(date.getDate()).padStart(2,"0");
}
function directoryView(events,query="",filter="all",sort="soonest",today=localDay()){
 const needle=String(query).toLocaleLowerCase().trim();
 const items=(Array.isArray(events)?events:[]).filter(e=>{
   const day=String(e.date||""),valid=validDay(day);
   const text=[e.name,e.date,e.note].map(x=>String(x??"")).join(" ").toLocaleLowerCase();
   if(!text.includes(needle))return false;
   const people=Array.isArray(e.people)?e.people:[];
   const needsReply=people.some(p=>p.rsvp_status!=="declined"&&p.status==="unpaid"&&!p.approved&&Number(p.share_cents)>0);
   const tasks=Array.isArray(e.tasks)?e.tasks:[];
   const needsAttention=!people.length||!(Number(e.total_cents)>0)||needsReply||
       tasks.some(t=>!t.completed)||people.some(p=>p.rsvp_status==="declined");
   if(filter==="upcoming")return valid&&day>=today;
   if(filter==="past")return valid&&day<today;
   if(filter==="needs-attention")return needsAttention;
   return true;
 });
 items.sort((a,b)=>{
   if(sort==="budget")return (Number(b.total_cents)||0)-(Number(a.total_cents)||0) || Number(a.id)-Number(b.id);
   if(sort==="latest")return String(b.date).localeCompare(String(a.date))||Number(a.id)-Number(b.id);
   // Earliest upcoming events first, past events below them.
   function key(e){return validDay(e.date)&&e.date>=today?0:1;}
   return key(a)-key(b)||String(a.date).localeCompare(String(b.date))||Number(a.id)-Number(b.id);
 });
 return items;
}
function explainShare(event,participantId){
 if(!event||!Array.isArray(event.people))throw Error("Select an event with participants.");
 const people=event.people;
 if(!people.length)throw Error("Add participants before explaining a split.");
 const total=Number(event.total_cents)||0;
 if(!Number.isSafeInteger(total)||total<0)throw Error("Invalid event budget.");
 const strategy=event.strategy==="weighted"?"weighted":"equal";
 const ordered=people.map(p=>({
   id:Number(p.id),name:String(p.name||""),recorded:Number(p.share_cents),
   effectiveWeight:strategy==="equal"?1:Number(p.weight)
 })).sort((a,b)=>a.id-b.id);
 if(ordered.some(p=>!Number.isSafeInteger(p.id)||p.id<1||
     !Number.isSafeInteger(p.effectiveWeight)||p.effectiveWeight<1||p.effectiveWeight>10))
   throw Error("Invalid participant weights.");
 const sumWeight=ordered.reduce((v,p)=>v+p.effectiveWeight,0);
 const entries=ordered.map(p=>{
   const numerator=total*p.effectiveWeight;
   return {...p,baseCents:Math.floor(numerator/sumWeight),remainder:numerator%sumWeight};
 });
 const leftover=total-entries.reduce((sum,p)=>sum+p.baseCents,0);
 if(leftover<0||leftover>=entries.length)throw Error("Rounding allocation is invalid.");
 const ranked=entries.slice().sort((a,b)=>b.remainder-a.remainder||a.id-b.id);
 const bonuses=new Set(ranked.slice(0,leftover).map(p=>p.id));
 const selected=entries.find(p=>p.id===Number(participantId));
 if(!selected)throw Error("Participant not found in this event.");
 const roundingCents=bonuses.has(selected.id)?1:0;
 const expectedCents=selected.baseCents+roundingCents;
 const allocatedTotal=entries.reduce((sum,p)=>sum+p.recorded,0);
 return {
   name:selected.name,participantId:selected.id,peopleCount:entries.length,
   totalCents:total,strategy,effectiveWeight:selected.effectiveWeight,totalWeight:sumWeight,
   baseCents:selected.baseCents,roundingCents,expectedCents,recordedCents:selected.recorded,
   remainder:selected.remainder,allocationBalanced:allocatedTotal===total,
   consistent:selected.recorded===expectedCents&&allocatedTotal===total,
   formula:"Floor of (budget cents × effective attendance weight ÷ sum of weights), plus one possible remainder cent. Ties go to lower participant IDs."
 };
}
if(typeof module!=="undefined"&&module.exports)
 module.exports={validDay,localDay,directoryView,explainShare};
