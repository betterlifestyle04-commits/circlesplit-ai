const {test}=require("node:test");
const assert=require("node:assert/strict");
const {insightData,csvCell,csvText}=require("../static/insights.js");
test("funding insights separate captured and simulated contributions",()=>{
 const events=[{id:1,name:"Volleyball",date:"2026-11-06",total_cents:22000,sandbox_cents:1100,
 simulated_cents:1100,people:[{share_cents:1100,approved:true},{share_cents:20900,approved:false}]}];
 const x=insightData(events);
 assert.equal(x.budget,22000);assert.equal(x.confirmed,1100);assert.equal(x.outstanding,20900);
 assert.equal(x.simulated,1100);assert.equal(x.approved,1);assert.equal(x.issues,0);
 assert.equal(x.rate,5);assert.equal(x.events[0].balanced,true);
});
test("report flags inconsistent shares rather than presenting erroneous totals",()=>{
 const x=insightData([{id:2,total_cents:100,people:[{share_cents:44},{share_cents:55}]}]);
 assert.equal(x.issues,1);assert.equal(x.events[0].balanced,false);
});
test("CSV exports escape formulas quotes and multiline content",()=>{
 assert.equal(csvCell('=HYPERLINK("evil")'),"\"'=HYPERLINK(\"\"evil\"\")\"");
 assert.equal(csvCell(" \t+1+2"),"\"' \t+1+2\"");
 assert.equal(csvCell("text,quote\"yes"),"\"text,quote\"\"yes\"");
 assert.ok(csvText([["name","amount"],["Test","11.00"]]).includes("11.00"));
});
