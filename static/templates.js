"use strict";
/* Read-only Quick Start previews. Server catalog and validation are authoritative. */
function validTemplateDate(day){
 if(typeof day!=="string"||!/^\d{4}-\d{2}-\d{2}$/.test(day))return false;
 const parts=day.split("-").map(Number);
 const dt=new Date(Date.UTC(parts[0],parts[1]-1,parts[2]));
 return dt.getUTCFullYear()===parts[0]&&dt.getUTCMonth()===parts[1]-1&&dt.getUTCDate()===parts[2];
}
function templatePreview(template,includeExpenses=true,includeTasks=true){
 if(!template||typeof template!=="object"||!Array.isArray(template.expenses)||
    !Array.isArray(template.tasks))throw Error("Invalid quick-start template.");
 const expenses=includeExpenses?template.expenses:[],tasks=includeTasks?template.tasks:[];
 const estimatedCents=expenses.reduce((sum,e)=>{
  if(!Number.isSafeInteger(e.cents)||e.cents<1||e.cents>10000000)
   throw Error("Template contains an invalid cost.");
  return sum+e.cents;
 },0);
 if(estimatedCents>10000000)throw Error("Template total exceeds the demo limit.");
 return {expenses,tasks,estimatedCents,expenseCount:expenses.length,taskCount:tasks.length};
}
function templateRequestPayload(key,name,date,includeExpenses,includeTasks,requestKey){
 if(typeof key!=="string"||!key||
    typeof name!=="string"||name.trim().length<3||name.trim().length>90||
    !validTemplateDate(date)||
    typeof includeExpenses!=="boolean"||typeof includeTasks!=="boolean"||
    typeof requestKey!=="string"||
    !/^[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(requestKey))
  throw Error("Check the event name and date before creating the template.");
 return {key,body:{name:name.trim(),date,include_expenses:includeExpenses,
                    include_tasks:includeTasks,request_key:requestKey}};
}
if(typeof module!=="undefined"&&module.exports)
 module.exports={validTemplateDate,templatePreview,templateRequestPayload};
