const {test}=require("node:test");
const assert=require("node:assert/strict");
const {validEventDate,prepareEventDetails}=require("../static/event-details.js");
const original={name:"Volleyball night",date:"2026-11-15",note:"Meet at 7pm"};
test("event details preflight trims fields and includes stale-write protection",()=>{
 const result=prepareEventDetails("  Volleyball Saturday  ","2026-11-22","  New place  ",original);
 assert.equal(result.changed,true);
 assert.deepEqual(result.body,{name:"Volleyball Saturday",date:"2026-11-22",note:"New place",
   expected_name:"Volleyball night",expected_date:"2026-11-15",expected_note:"Meet at 7pm"});
 assert.equal(original.name,"Volleyball night");
});
test("no-op event details are detected",()=>{
 const result=prepareEventDetails(original.name,original.date,original.note,original);
 assert.equal(result.changed,false);
});
test("real dates, not impossible calendar dates",()=>{
 assert.equal(validEventDate("2028-02-29"),true);
 for(const value of ["2026-02-29","2026-02-30","2026-11-31","2026-13-04","2026/11/03",""]){
  assert.equal(validEventDate(value),false,value);
  assert.throws(()=>prepareEventDetails("Ready event",value,"",original),/date/);
 }
});
test("invalid names, descriptions and stale snapshots fail locally",()=>{
 assert.throws(()=>prepareEventDetails(" a ","2026-11-16","",original),/Name/);
 assert.throws(()=>prepareEventDetails("Good event","2026-11-16","a".repeat(181),original),/Description/);
 assert.throws(()=>prepareEventDetails("Good event","2026-11-16","",null),/Reload/);
});
