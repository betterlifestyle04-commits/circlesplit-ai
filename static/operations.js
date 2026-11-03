"use strict";
function taskProgress(tasks){const a=Array.isArray(tasks)?tasks:[];const done=a.filter(x=>!!x.completed).length;return {total:a.length,done,percent:a.length?Math.round(100*done/a.length):0};}
function icsEscape(s){return String(s??"").replace(/\\/g,"\\\\").replace(/\r\n|\r|\n/g,"\\n").replace(/;/g,"\\;").replace(/,/g,"\\,");}
function validDate(s){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(s))throw Error("Event date must use YYYY-MM-DD");
 const [y,m,d]=s.split("-").map(Number),utc=new Date(Date.UTC(y,m-1,d));
 if(utc.getUTCFullYear()!==y||utc.getUTCMonth()+1!==m||utc.getUTCDate()!==d)throw Error("Invalid calendar date");
 return utc;
}
function icsDate(d){return d.getUTCFullYear()+String(d.getUTCMonth()+1).padStart(2,"0")+String(d.getUTCDate()).padStart(2,"0");}
function exportIcs(e,clock=new Date()){
 if(!e||!Number.isSafeInteger(Number(e.id)))throw Error("Select an event");
 const start=validDate(e.date),end=new Date(start.getTime()+86400000);
 const stamp=clock.toISOString().replace(/[-:]/g,"").replace(/\.\d{3}/,"");
 const lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//CircleSplit AI//Demo//EN","CALSCALE:GREGORIAN","BEGIN:VEVENT",
 "UID:circlesplit-"+Number(e.id)+"@demo.invalid","DTSTAMP:"+stamp,"DTSTART;VALUE=DATE:"+icsDate(start),
 "DTEND;VALUE=DATE:"+icsDate(end),"SUMMARY:"+icsEscape(e.name),
 "DESCRIPTION:"+icsEscape((e.note||"")+"\nCircleSplit AI sandbox-only event. No real payments."),
 "END:VEVENT","END:VCALENDAR"];
 return lines.map(function(line){
  const chars=Array.from(line);let out="",n=0;
  for(const ch of chars){const code=ch.codePointAt(0),size=code>65535?4:code>2047?3:code>127?2:1;
   if(n+size>75){out+="\r\n ";n=1}out+=ch;n+=size;}
  return out;
 }).join("\r\n")+"\r\n";
}
if(typeof module!=="undefined"&&module.exports)module.exports={taskProgress,icsEscape,validDate,exportIcs};