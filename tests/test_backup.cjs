const {test}=require("node:test"),assert=require("node:assert/strict");
const {inspectPlanningBackup}=require("../static/backup.js");
const example={app:"CircleSplit AI",kind:"planning-backup",schema_version:1,currency:"USD",
 exported_at:"2026-11-03T12:00:00Z",events:[{name:"Volleyball evening",date:"2026-11-17",
 note:"For friends",strategy:"weighted",
 expenses:[{title:"Court fee",cents:16000,category:"venue"}],
 people:[{name:"Alex",weight:2},{name:"Taylor",weight:1}],
 tasks:[{title:"Arrange the court"}],
 planning:{ceiling_cents:25000,reserve_percent:10}}]};
const copy=()=>JSON.parse(JSON.stringify(example));
test("inspects a planning-only backup without modifying input",()=>{
 const raw=copy(),original=JSON.stringify(raw),p=inspectPlanningBackup(raw);
 assert.deepEqual(p,{events:1,people:2,expenses:1,tasks:1,plannedCents:16000});
 assert.equal(JSON.stringify(raw),original);
});
test("refuses financial status, invitations, capture identifiers or extra keys",()=>{
 for(const property of ["payments","transactions","approved","status","rsvp_status","capture_id","token"]){
  const raw=copy();raw.events[0][property]=true;
  assert.throws(()=>inspectPlanningBackup(raw),/unsupported field/);
 }
 const raw=copy();raw.events[0].people[0].approved=true;
 assert.throws(()=>inspectPlanningBackup(raw),/unsupported field/);
});
test("rejects bad formats, currency and unsupported schema versions",()=>{
 const r=copy();r.currency="NOK";assert.throws(()=>inspectPlanningBackup(r),/planning-backup/);
 const v=copy();v.schema_version=2;assert.throws(()=>inspectPlanningBackup(v),/planning-backup/);
 const x=copy();x.events[0].date="2026-02-30";assert.throws(()=>inspectPlanningBackup(x),/calendar date/);
});
test("rejects duplicate people, duplicate tasks, invalid weights and negative cents",()=>{
 const r=copy();r.events[0].people[1].name="  alex ";
 assert.throws(()=>inspectPlanningBackup(r),/duplicate participant/);
 const t=copy();t.events[0].tasks.push({title:" arrange the COURT "});
 assert.throws(()=>inspectPlanningBackup(t),/duplicate task/);
 const v=copy();v.events[0].people[0].weight=11;
 assert.throws(()=>inspectPlanningBackup(v),/out of range/);
 const c=copy();c.events[0].expenses[0].cents=-1;
 assert.throws(()=>inspectPlanningBackup(c),/out of range/);
});
test("limit enforcement and empty events",()=>{
 const empty=copy();empty.events=[];
 assert.throws(()=>inspectPlanningBackup(empty),/1–25/);
 const big=copy();big.events=Array.from({length:26},()=>copy().events[0]);
 assert.throws(()=>inspectPlanningBackup(big),/1–25/);
});
