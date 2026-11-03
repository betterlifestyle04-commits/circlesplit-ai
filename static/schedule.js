"use strict";
/* Shared local agenda preflight; server validates the final schedule. */
function minutes(time){
 if(typeof time!=="string"||!/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(time))
   throw Error("Enter a 24-hour time such as 09:30.");
 return Number(time.slice(0,2))*60+Number(time.slice(3));
}
function agendaInput(title,start_time,end_time,note=""){
 const name=String(title??"").trim(),details=String(note??"").trim();
 if(name.length<3||name.length>100)throw Error("Agenda title must contain 3–100 characters.");
 if(details.length>160)throw Error("Agenda note cannot exceed 160 characters.");
 if(minutes(start_time)>=minutes(end_time))throw Error("Agenda end time must be later on the same day.");
 return {title:name,start_time,end_time,note:details};
}
function agendaOverlap(slots,start,end,excludeId=null){
 const a=minutes(start),b=minutes(end);
 return (Array.isArray(slots)?slots:[]).some(row=>
   row.id!==excludeId&&a<minutes(row.end_time)&&b>minutes(row.start_time));
}
function agendaSorted(slots){
 return [...(Array.isArray(slots)?slots:[])].sort((a,b)=>
   minutes(a.start_time)-minutes(b.start_time)||Number(a.id||0)-Number(b.id||0));
}
if(typeof module!=="undefined"&&module.exports)
 module.exports={minutes,agendaInput,agendaOverlap,agendaSorted};
