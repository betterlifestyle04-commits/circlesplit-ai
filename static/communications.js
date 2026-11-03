"use strict";
function rsvpStats(people){
 const stats={total:0,going:0,maybe:0,declined:0,pending:0};
 for(const p of Array.isArray(people)?people:[]){
  const status=["going","maybe","declined"].includes(p.rsvp_status)?p.rsvp_status:"pending";
  stats[status]++;stats.total++;
 }
 return stats;
}
function normalizeLine(value,max=200){
 return String(value??"").replace(/[\r\n\t]+/g," ").replace(/\s+/g," ").trim().slice(0,max);
}
function draftEventUpdate(event,kind){
 if(!event)throw Error("Select an event first");
 const name=normalizeLine(event.name,90),date=normalizeLine(event.date,20),
       note=normalizeLine(event.note,200),tasks=Array.isArray(event.tasks)?event.tasks:[],
       stats=rsvpStats(event.people),remaining=tasks.filter(t=>!t.completed).length;
 const intro="CircleSplit AI — fictional event communication draft\n"+
  "Event: "+name+"\nDate: "+date+"\n";
 let content="";
 if(kind==="announcement"){
   content="We're planning this group activity. "+(note?"Details: "+note+"\n":"")+
    "Please check the practical details with the organizer before making plans.\n"+
    "Attendance responses so far: "+stats.going+" Going, "+stats.maybe+" Maybe, "+
    stats.declined+" Can't attend, "+stats.pending+" Not answered.";
 }else if(kind==="rsvp"){
   content="If you have a private invitation link, please open it and update your attendance (Going, Maybe or Can't attend). "+
    "Don't forward your private link or use somebody else's invitation.\n"+
    "Responses remaining: "+stats.pending+". The organizer will review any declines.";
 }else if(kind==="preparation"){
   content="Event preparation update: "+remaining+" of "+tasks.length+
     " checklist tasks remain. Please coordinate venue and equipment details with the organizer. "+
     "Nothing is confirmed merely because a planning task exists.";
 }else throw Error("Unknown draft template");
 return intro+content+"\n\nIMPORTANT: This is an editable draft only. No message has been sent. "+
 "The event and amounts are fictional sandbox test data. This is NOT an invoice, "+
 "payment request, or confirmation of a real booking.";
}
if(typeof module!=="undefined"&&module.exports)
 module.exports={rsvpStats,normalizeLine,draftEventUpdate};