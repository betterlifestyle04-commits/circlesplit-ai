"use strict";
/* A local preflight only. Server validation is authoritative. */
const BACKUP_ALLOWED={
 root:["app","kind","schema_version","currency","exported_at","events"],
 event:["name","date","note","strategy","expenses","people","tasks","agenda","planning"],
 expense:["title","cents","category"],
 person:["name","weight"],task:["title"],
 agenda:["start_time","end_time","title","note"],
 planning:["ceiling_cents","reserve_percent"]
};
function backupRecord(o,allowed,label){
 if(!o||Array.isArray(o)||typeof o!=="object")throw Error(label+" must be an object.");
 for(const key of Object.keys(o))if(!allowed.includes(key))
   throw Error(label+" contains unsupported field '"+key+"'. Financial and approval records cannot be imported.");
}
function backupString(x,min,max,label){
 if(typeof x!=="string"||x.trim().length<min||x.length>max)
  throw Error(label+" must be "+min+"–"+max+" characters.");
 return x;
}
function backupInteger(n,min,max,label){
 if(!Number.isSafeInteger(n)||n<min||n>max)throw Error(label+" is out of range.");
 return n;
}
function backupDate(value){
 if(!/^\d{4}-\d{2}-\d{2}$/.test(value))throw Error("Invalid event date.");
 const [year,month,day]=value.split("-").map(Number);
 const result=new Date(Date.UTC(year,month-1,day));
 if(result.getUTCFullYear()!==year||result.getUTCMonth()!==month-1||result.getUTCDate()!==day)
  throw Error("Invalid calendar date.");
}
function inspectPlanningBackup(data){
 backupRecord(data,BACKUP_ALLOWED.root,"Backup");
 if(data.app!=="CircleSplit AI"||data.kind!=="planning-backup"||
    data.schema_version!==1||data.currency!=="USD")
  throw Error("This is not a CircleSplit planning-backup v1 in USD.");
 backupString(data.exported_at,10,45,"Export timestamp");
 if(!Array.isArray(data.events)||!data.events.length||data.events.length>25)
  throw Error("Backup must contain 1–25 events.");
 let people=0,expenses=0,tasks=0,agenda=0,plannedCents=0;
 for(const [i,e] of data.events.entries()){
  const label="Event "+(i+1);
  backupRecord(e,BACKUP_ALLOWED.event,label);
  backupString(e.name,3,90,label+" name");
  backupString(e.date,10,10,label+" date");
  backupDate(e.date);
  backupString(e.note,0,180,label+" description");
  if(!["equal","weighted"].includes(e.strategy))throw Error(label+": unknown split strategy.");
  if(!Array.isArray(e.expenses)||e.expenses.length>200||
     !Array.isArray(e.people)||e.people.length>200||
     !Array.isArray(e.tasks)||e.tasks.length>40||
     (e.agenda!==undefined&&(!Array.isArray(e.agenda)||e.agenda.length>20)))
   throw Error(label+": too many expenses, participants or tasks.");
  const names=new Set(),taskNames=new Set();
  let total=0;
  for(const x of e.expenses){
   backupRecord(x,BACKUP_ALLOWED.expense,"Expense");
   backupString(x.title,2,120,"Expense title");
   total+=backupInteger(x.cents,1,10000000,"Expense amount");
   if(!["venue","equipment","food","travel","services","other"].includes(x.category))
    throw Error(label+": unsupported expense category.");
  }
  if(total>10000000)throw Error(label+": planned budget exceeds the demo limit.");
  for(const p of e.people){
   backupRecord(p,BACKUP_ALLOWED.person,"Participant");
   const key=backupString(p.name,2,60,"Participant name").trim().toLowerCase();
   if(names.has(key))throw Error(label+": duplicate participant names.");
   names.add(key);backupInteger(p.weight,1,10,"Participant weight");
  }
  for(const t of e.tasks){
   backupRecord(t,BACKUP_ALLOWED.task,"Task");
   const key=backupString(t.title,3,120,"Task name").trim().toLowerCase();
   if(taskNames.has(key))throw Error(label+": duplicate task names.");
   taskNames.add(key);
  }
  const slots=e.agenda||[];
  const ordered=[];
  for(const item of slots){
   backupRecord(item,BACKUP_ALLOWED.agenda,"Agenda item");
   backupString(item.title,3,100,"Agenda title");
   backupString(item.note,0,160,"Agenda note");
   for(const key of ["start_time","end_time"]){
    if(typeof item[key]!=="string"||!/^(?:[01][0-9]|2[0-3]):[0-5][0-9]$/.test(item[key]))
     throw Error(label+": invalid agenda time.");
   }
   if(item.start_time>=item.end_time)throw Error(label+": agenda end time must be later.");
   ordered.push(item);
  }
  ordered.sort((a,b)=>a.start_time.localeCompare(b.start_time));
  for(let k=1;k<ordered.length;k++){
   if(ordered[k-1].end_time>ordered[k].start_time)
    throw Error(label+": overlapping agenda items.");
  }
  backupRecord(e.planning,BACKUP_ALLOWED.planning,"Planning target");
  if(e.planning.ceiling_cents!==null)
   backupInteger(e.planning.ceiling_cents,1,10000000,"Spending ceiling");
  backupInteger(e.planning.reserve_percent,0,50,"Reserve percentage");
  people+=e.people.length;expenses+=e.expenses.length;tasks+=e.tasks.length;
  agenda+=slots.length;plannedCents+=total;
 }
 if(people>1000||expenses>500||tasks>500||agenda>250)throw Error("Backup exceeds combined record limits.");
 return {events:data.events.length,people,expenses,tasks,agenda,plannedCents};
}
if(typeof module!=="undefined"&&module.exports)
 module.exports={inspectPlanningBackup,backupDate};
