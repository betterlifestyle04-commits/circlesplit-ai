"use strict";
/* Browser-side preflight only. The server validates and commits edits. */
function validateExpenseEdit(title,amount,category){
 const name=String(title??"").trim(),raw=String(amount??"").trim();
 if(name.length<2||name.length>120)throw Error("Expense name must contain 2–120 characters.");
 if(!/^\d+(?:\.\d{1,2})?$/.test(raw))throw Error("Use a USD amount with at most 2 decimal places.");
 const parts=raw.split(".");
 const cents=Number(parts[0])*100+Number((parts[1]||"").padEnd(2,"0"));
 if(!Number.isSafeInteger(cents)||cents<1||cents>10000000)throw Error("Expense must be between $0.01 and $100,000.");
 if(!["venue","equipment","food","travel","services","other"].includes(category))
   throw Error("Unknown expense category.");
 return {title:name,amount:(cents/100).toFixed(2),category};
}
function validateParticipantEdit(name,weight){
 const trimmed=String(name??"").trim();
 if(trimmed.length<2||trimmed.length>60)throw Error("Participant name must contain 2–60 characters.");
 if(typeof weight==="string"&&!/^\d+$/.test(weight.trim()))
   throw Error("Weight must be a whole number from 1 to 10.");
 const n=Number(weight);
 if(!Number.isInteger(n)||n<1||n>10)throw Error("Weight must be a whole number from 1 to 10.");
 return {name:trimmed,weight:n};
}
if(typeof module!=="undefined"&&module.exports)
 module.exports={validateExpenseEdit,validateParticipantEdit};
