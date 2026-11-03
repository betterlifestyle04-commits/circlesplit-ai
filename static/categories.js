"use strict";
/* Pure, read-only categorization helpers; never modify approved amounts. */
const CATEGORY_KEYS=["venue","equipment","food","travel","services","other"];
const CATEGORY_LABELS={
 venue:"Venue & space",equipment:"Equipment",food:"Food & drinks",
 travel:"Travel",services:"Services",other:"Other"
};
function normalizeCategory(key){
 return CATEGORY_KEYS.includes(key)?key:"other";
}
function categoryOptions(value){
 const current=normalizeCategory(value);
 return CATEGORY_KEYS.map(key=>'<option value="'+key+'"'+(key===current?' selected':'')+'>'+CATEGORY_LABELS[key]+'</option>').join("");
}
function budgetCategories(expenses){
 const totals=Object.fromEntries(CATEGORY_KEYS.map(key=>[key,{key,label:CATEGORY_LABELS[key],cents:0,count:0}]));
 for(const row of Array.isArray(expenses)?expenses:[]){
  const k=normalizeCategory(row.category),cents=Number(row.cents);
  if(!Number.isSafeInteger(cents)||cents<0)throw Error("Invalid expense amount in budget");
  totals[k].cents+=cents;
  totals[k].count++;
 }
 const total=Object.values(totals).reduce((n,row)=>n+row.cents,0);
 return {totalCents:total,categories:CATEGORY_KEYS.map(key=>({
  ...totals[key],
  percent:total?Math.round(totals[key].cents/total*100):0
 }))};
}
function allBudgetCategories(events){
 return budgetCategories((Array.isArray(events)?events:[]).flatMap(e=>Array.isArray(e.expenses)?e.expenses:[]));
}
if(typeof module!=="undefined"&&module.exports){
 module.exports={CATEGORY_KEYS,CATEGORY_LABELS,normalizeCategory,categoryOptions,budgetCategories,allBudgetCategories};
}
