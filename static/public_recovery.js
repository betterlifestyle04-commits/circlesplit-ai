"use strict";
/* Public fictional resilience planner. Pure integer-cent math; never uses APIs
 * or writes to events, permissions, invitations, approvals or payments. */
(function(root){
 function exactSplit(total, members, method){
  if(!Number.isSafeInteger(total)||total<0||
     !Array.isArray(members)||members.length<1||members.length>200||
     !["equal","weighted"].includes(method)){
   throw Error("Invalid public split inputs");
  }
  // Reject invalid records before sorting or reading their IDs in a comparator.
  // Keep this guard independent of any caller-side localStorage validation.
  if(members.some(x=>!x||typeof x!=="object"||
      !Number.isSafeInteger(x.id)||x.id<1||
      !Number.isInteger(x.weight)||x.weight<1||x.weight>10)){
   throw Error("Invalid fictional attendees");
  }
  const p=[...members].sort((a,b)=>a.id-b.id);
  if(new Set(p.map(x=>x.id)).size!==p.length)
   throw Error("Invalid fictional attendees");
  const w=p.map(x=>method==="equal"?1:x.weight);
  const sum=w.reduce((n,x)=>n+x,0);
  if(total>Math.floor(Number.MAX_SAFE_INTEGER/10))throw Error("Budget exceeds safe demo limits");
  const shares=w.map(x=>Math.floor(total*x/sum));
  let remainder=total-shares.reduce((n,x)=>n+x,0);
  const ranked=w.map((x,i)=>({i,rem:total*x%sum,id:p[i].id}))
   .sort((a,b)=>b.rem-a.rem||a.id-b.id);
  for(let i=0;i<remainder;i++)shares[ranked[i].i]++;
  if(shares.reduce((n,x)=>n+x,0)!==total)throw Error("Share calculation did not balance");
  return shares;
 }
 function preview({total_cents,people,strategy,maximum_absent,max_share_cents}){
  if(!Number.isSafeInteger(maximum_absent)||maximum_absent<0||maximum_absent>20||
     !Number.isSafeInteger(max_share_cents)||max_share_cents<1||max_share_cents>10000000||
     !Array.isArray(people)||!people.length||people.length>200){
   throw Error("Choose a valid fictional group, no-show count and cap");
  }
  const all=people.map(x=>({id:x.id,weight:x.weight}));
  const baseline=exactSplit(total_cents,all,strategy);
  const initialPeak=Math.max(...baseline);
  const maxId=Math.max(...all.map(x=>x.id));
  if(maxId>Number.MAX_SAFE_INTEGER-51)throw Error("Participant IDs exceed demo limits");
  const effective=x=>strategy==="equal"?1:x.weight;
  const anchor=[...all].sort((a,b)=>effective(b)-effective(a)||a.id-b.id)[0];
  const candidates=all.filter(x=>x.id!==anchor.id)
   .sort((a,b)=>effective(b)-effective(a)||b.id-a.id);
  const limit=Math.min(maximum_absent,candidates.length);
  const projections=[];
  let firstTargetBreachAtAbsences=null;
  for(let absent=0;absent<=limit;absent++){
   const removed=new Set(candidates.slice(0,absent).map(x=>x.id));
   const remaining=all.filter(x=>!removed.has(x.id));
   const shares=exactSplit(total_cents,remaining,strategy);
   const peak=Math.max(...shares);
   const over=peak>max_share_cents;
   if(over&&firstTargetBreachAtAbsences===null)firstTargetBreachAtAbsences=absent;
   const maxReplacements=Math.min(50,200-remaining.length);
   let minNeeded=over?null:0, bestPeak=peak, bestCount=0, tested=1;
   if(over){
    const projected=[...remaining];
    for(let n=1;n<=maxReplacements;n++){
     projected.push({id:maxId+n,weight:1});
     const nextPeak=Math.max(...exactSplit(total_cents,projected,strategy));
     tested++;
     if(nextPeak<bestPeak){bestPeak=nextPeak;bestCount=n;}
     if(nextPeak<=max_share_cents){
      minNeeded=n;bestPeak=nextPeak;bestCount=n;break;
     }
    }
   }
   projections.push({
    absent_people:absent,remaining_people:remaining.length,
    largest_share_cents:peak,smallest_share_cents:Math.min(...shares),
    over_target:over,minimum_replacements_needed:minNeeded,
    replacements_feasible:minNeeded!==null,maximum_replacements_considered:maxReplacements,
    best_replacement_count:bestCount,best_replacement_largest_share_cents:bestPeak,
    replacement_gap_cents:Math.max(0,bestPeak-max_share_cents),
    replacement_candidates_tested:tested
   });
  }
  return {
   mode:"BROWSER_LOCAL_FICTIONAL_DEMO",read_only:true,budget_cents:total_cents,
   strategy,cap_cents:max_share_cents,current_people:people.length,
   current_largest_share_cents:initialPeak,tested_maximum_absent:limit,
   first_target_breach_at_absences:firstTargetBreachAtAbsences,projections
  };
 }
 const api={exactSplit,preview};
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 else root.CircleSplitPublicRecovery=api;
})(typeof window!=="undefined"?window:{});
