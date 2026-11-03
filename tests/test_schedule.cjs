const {test}=require("node:test"),assert=require("node:assert/strict");
const {minutes,agendaInput,agendaOverlap,agendaSorted}=require("../static/schedule.js");
test("24 hour local time validated",()=>{
 assert.equal(minutes("00:00"),0);assert.equal(minutes("23:59"),1439);
 for(const x of ["24:00","9:30","12:60","12:5","-1:30","11:99"]){
   assert.throws(()=>minutes(x),/24-hour/);
 }
});
test("slot validation trims strings and rejects overnight or invalid lengths",()=>{
 assert.deepEqual(agendaInput("  Welcome  ","09:00","09:30","  Meet at entrance "),
  {title:"Welcome",start_time:"09:00",end_time:"09:30",note:"Meet at entrance"});
 for(const [a,b] of [["09:00","09:00"],["10:00","09:59"],["23:59","00:30"]])
   assert.throws(()=>agendaInput("Session",a,b),/later/);
 assert.throws(()=>agendaInput("Hi","09:00","10:00"),/title/);
 assert.throws(()=>agendaInput("Session","09:00","10:00","x".repeat(161)),/note/);
});
test("adjacent slots do not overlap and genuine overlaps do",()=>{
 const slots=[{id:1,start_time:"09:00",end_time:"10:00"},{id:2,start_time:"10:00",end_time:"11:00"}];
 assert.equal(agendaOverlap(slots,"11:00","12:00"),false);
 assert.equal(agendaOverlap(slots,"09:30","10:30"),true);
 assert.equal(agendaOverlap(slots,"09:15","09:45",1),false);
 assert.equal(agendaOverlap(slots,"09:15","10:15",1),true);
});
test("sorting is deterministic and leaves original unchanged",()=>{
 const x=[{id:3,start_time:"13:00"},{id:1,start_time:"09:00"},{id:2,start_time:"09:00"}];
 assert.deepEqual(agendaSorted(x).map(e=>e.id),[1,2,3]);
 assert.equal(x[0].id,3);
});
