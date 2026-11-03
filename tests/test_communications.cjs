const {test}=require("node:test");
const assert=require("node:assert/strict");
const {rsvpStats,normalizeLine,draftEventUpdate}=require("../static/communications.js");
const e={name:"Volleyball",date:"2026-11-07",note:"Twenty friends in a hall",
 people:[{name:"Alex",rsvp_status:"going"},{name:"Sam",rsvp_status:"declined"},
 {name:"Taylor",rsvp_status:"maybe"},{name:"Riley",rsvp_status:"pending"}],
 tasks:[{completed:true},{completed:false}]};
test("response counts always include all participants",()=>{
 assert.deepEqual(rsvpStats(e.people),{total:4,going:1,maybe:1,declined:1,pending:1});
 assert.deepEqual(rsvpStats([]),{total:0,going:0,maybe:0,declined:0,pending:0});
});
test("announcements are private-name-free drafts, never payment requests",()=>{
 const t=draftEventUpdate(e,"announcement");
 assert.match(t,/1 Going, 1 Maybe, 1 Can't attend, 1 Not answered/);
 assert.match(t,/No message has been sent/);
 assert.match(t,/NOT an invoice/);
 assert.ok(!t.includes("Alex")&&!t.includes("Taylor"));
});
test("rsvp and preparation messages do not contain bearer URLs or participant names",()=>{
 for(const kind of ["rsvp","preparation"]){
  const t=draftEventUpdate(e,kind);
  assert.match(t,/fictional sandbox/);
  assert.ok(!t.includes("http")&&!t.includes("Alex"));
 }
 assert.match(draftEventUpdate(e,"preparation"),/1 of 2 checklist tasks remain/);
 assert.throws(()=>draftEventUpdate(e,"payment"),/Unknown/);
});
test("single-line normalization prevents newline copying into template headers",()=>{
 assert.equal(normalizeLine("  Event\\nVenue\t update  ".replace("\\n","\n")),"Event Venue update");
});