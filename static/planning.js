"use strict";
/* Advisory event targets: no mutation of shares, approvals or checkout amounts. */
function parseCeilingCents(input){
 const text=String(input??"").trim();
 if(!text)return null;
 if(!/^\d+(?:\.\d{1,2})?$/.test(text))throw Error("Enter a positive USD amount with at most two decimals");
 const parts=text.split(".");
 const amount=Number(parts[0])*100+Number((parts[1]||"").padEnd(2,"0"));
 if(!Number.isSafeInteger(amount)||amount<1||amount>10000000)
  throw Error("The spending ceiling must be between $0.01 and $100,000.00");
 return amount;
}
function budgetForecast(plannedCents,ceilingCents,reservePercent){
 if(!Number.isSafeInteger(plannedCents)||plannedCents<0||
   !Number.isInteger(reservePercent)||reservePercent<0||reservePercent>50||
   (ceilingCents!==null&&(!Number.isSafeInteger(ceilingCents)||ceilingCents<1)))
   throw Error("Invalid budget planning inputs");
 const reserveCents=Math.floor((plannedCents*reservePercent+99)/100);
 const projectedCents=plannedCents+reserveCents;
 const headroomCents=ceilingCents===null?null:ceilingCents-projectedCents;
 return {
   planned_cents:plannedCents,ceiling_cents:ceilingCents,
   reserve_percent:reservePercent,reserve_cents:reserveCents,
   projected_cents:projectedCents,headroom_cents:headroomCents,
   over_ceiling_cents:headroomCents===null?0:Math.max(0,-headroomCents),
   status:ceilingCents===null?"no_ceiling":headroomCents<0?"over_ceiling":"within_ceiling"
 };
}
function budgetPortfolio(events){
 const values=(Array.isArray(events)?events:[]).map(e=>{
   const p=e.planning||{};
   return budgetForecast(Number(e.total_cents)||0,
     p.ceiling_cents===undefined?null:p.ceiling_cents,
     p.reserve_percent||0);
 });
 return {
   events:values.length,
   withCeiling:values.filter(x=>x.ceiling_cents!==null).length,
   overCeiling:values.filter(x=>x.status==="over_ceiling").length,
   plannedCents:values.reduce((n,x)=>n+x.planned_cents,0),
   reserveCents:values.reduce((n,x)=>n+x.reserve_cents,0),
   projectedCents:values.reduce((n,x)=>n+x.projected_cents,0),
   overCeilingCents:values.reduce((n,x)=>n+x.over_ceiling_cents,0)
 };
}
if(typeof module!=="undefined"&&module.exports)
 module.exports={parseCeilingCents,budgetForecast,budgetPortfolio};
