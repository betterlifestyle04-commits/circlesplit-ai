"use strict";
/* Browser-only what-if copies. They are fictional draft plans, NEVER payment history.
   The original event and its simulated contributions must remain untouched. */
(function(root){
 const MAX_ID=1000000000000;
 const SUFFIX=" (what-if draft)";
 function computeShares(total, people, strategy){
  if(!people.length)return;
  const ordered=[...people].sort((a,b)=>a.id-b.id);
  const weights=ordered.map(p=>strategy==="weighted"?p.weight:1);
  const divisor=weights.reduce((sum,n)=>sum+n,0);
  const shares=weights.map(weight=>Math.floor(total*weight/divisor));
  let remainder=total-shares.reduce((sum,n)=>sum+n,0);
  const ranking=weights.map((weight,index)=>({
   index,id:ordered[index].id,remainder:(total*weight)%divisor
  })).sort((a,b)=>b.remainder-a.remainder||a.id-b.id);
  for(let i=0;i<remainder;i++)shares[ranking[i].index]++;
  ordered.forEach((p,i)=>{p.share_cents=shares[i];});
 }
 function duplicateAsDraft(data,sourceEventId,validator){
  if(!validator||typeof validator.validateModel!=="function")
   throw Error("Fictional planning validator unavailable");
  // Never modify source data or trust unvalidated localStorage input.
  const clone=validator.validateModel(data);
  const source=clone.events.find(e=>e.id===sourceEventId);
  if(!source)throw Error("Select an existing fictional event to copy");
  if(clone.events.length>=25)throw Error("Maximum 25 fictional events per demo");
  const currentPeople=clone.events.reduce((sum,e)=>sum+e.people.length,0);
  const currentExpenses=clone.events.reduce((sum,e)=>sum+e.expenses.length,0);
  if(currentPeople+source.people.length>1000)
   throw Error("Copy would exceed the 1,000-person demo limit");
  if(currentExpenses+source.expenses.length>500)
   throw Error("Copy would exceed the 500-expense demo limit");
  const needed=1+source.people.length+source.expenses.length;
  if(clone.next+needed>MAX_ID)
   throw Error("No more safe fictional record IDs can be allocated");
  let next=clone.next;
  const draft={
   id:++next,
   name:source.name.slice(0,90-SUFFIX.length).trimEnd()+SUFFIX,
   date:source.date,
   strategy:source.strategy,
   expenses:source.expenses.map(x=>({
    id:++next,title:x.title,cents:x.cents
   })),
   people:source.people.map(p=>({
    id:++next,name:p.name,weight:p.weight,
    share_cents:0,approved:false,status:"unpaid"
   }))
  };
  const budget=draft.expenses.reduce((sum,e)=>sum+e.cents,0);
  computeShares(budget,draft.people,draft.strategy);
  clone.next=next;
  clone.events.unshift(draft);
  // Fail closed if a future schema change would let an invalid copy pass.
  const result=validator.validateModel(clone);
  return {
   model:result,
   newEventId:draft.id,
   summary:{
    sourceEventId,
    newEventId:draft.id,
    budget_cents:budget,
    participants:draft.people.length,
    expenses:draft.expenses.length,
    approvals_copied:0,
    payments_copied:0,
    mode:"BROWSER_LOCAL_FICTIONAL_DRAFT"
   }
  };
 }
 // Read-only aggregate comparison: no participant identity matching,
 // consent transfer, payment settlement, or provider lookups.
 function compareEvents(data,baselineId,alternativeId,validator){
  if(!validator||typeof validator.validateModel!=="function")
   throw Error("Fictional planning validator unavailable");
  const clean=validator.validateModel(data);
  if(!Number.isSafeInteger(baselineId)||!Number.isSafeInteger(alternativeId)||
     baselineId===alternativeId)
   throw Error("Choose two different fictional events to compare");
  const baseline=clean.events.find(e=>e.id===baselineId);
  const alternative=clean.events.find(e=>e.id===alternativeId);
  if(!baseline||!alternative)
   throw Error("Choose two existing fictional events to compare");
  function metrics(e){
   const budget=e.expenses.reduce((sum,x)=>sum+x.cents,0);
   const n=e.people.length;
   const shares=e.people.map(p=>p.share_cents);
   const highest=n?Math.max(...shares):null;
   const lowest=n?Math.min(...shares):null;
   return {
    id:e.id,
    name:e.name,
    strategy:e.strategy,
    budget_cents:budget,
    participants:n,
    expenses:e.expenses.length,
    highest_share_cents:highest,
    lowest_share_cents:lowest,
    approved_count:e.people.filter(p=>p.approved).length,
    simulated_count:e.people.filter(p=>p.status==="demo_paid").length
   };
  }
  const before=metrics(baseline);
  const after=metrics(alternative);
  return {
   mode:"BROWSER_LOCAL_FICTIONAL_COMPARISON",
   read_only:true,
   before,after,
   delta:{
    budget_cents:after.budget_cents-before.budget_cents,
    participants:after.participants-before.participants,
    expenses:after.expenses-before.expenses,
    highest_share_cents:after.highest_share_cents===null||
      before.highest_share_cents===null?null:
      after.highest_share_cents-before.highest_share_cents,
    lowest_share_cents:after.lowest_share_cents===null||
      before.lowest_share_cents===null?null:
      after.lowest_share_cents-before.lowest_share_cents,
    approved_count:after.approved_count-before.approved_count,
    simulated_count:after.simulated_count-before.simulated_count
   }
  };
 }
 const api={duplicateAsDraft,compareEvents};
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 else root.CircleSplitPublicScenarios=api;
})(typeof window!=="undefined"?window:{});
