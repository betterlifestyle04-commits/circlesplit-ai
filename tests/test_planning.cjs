const {test}=require("node:test"),assert=require("node:assert/strict");
const {parseCeilingCents,budgetForecast,budgetPortfolio}=require("../static/planning.js");
test("valid ceiling amounts parse exactly to cents",()=>{
 assert.equal(parseCeilingCents(""),null);
 assert.equal(parseCeilingCents(" 250.45 "),25045);
 assert.equal(parseCeilingCents("1"),100);
 assert.equal(parseCeilingCents("100000.00"),10000000);
});
test("invalid ceilings fail closed",()=>{
 for(const bad of ["0","0.00","-1","1.234","1e3","NaN","100000.01","1,000","$10"])
  assert.throws(()=>parseCeilingCents(bad),/ceiling|positive USD/);
});
test("contingency rounds UP to whole cents and never alters base cost",()=>{
 const p=budgetForecast(101,110,5);
 assert.equal(p.planned_cents,101);
 assert.equal(p.reserve_cents,6);
 assert.equal(p.projected_cents,107);
 assert.equal(p.headroom_cents,3);
 assert.equal(p.status,"within_ceiling");
});
test("over ceiling reflects projected cost, not real debt",()=>{
 const p=budgetForecast(22000,23000,10);
 assert.equal(p.reserve_cents,2200);
 assert.equal(p.projected_cents,24200);
 assert.equal(p.over_ceiling_cents,1200);
 assert.equal(p.status,"over_ceiling");
 assert.equal(budgetForecast(22000,null,10).status,"no_ceiling");
});
test("portfolio sums projections but keeps unconfigured ceilings separate",()=>{
 const x=budgetPortfolio([
  {total_cents:22000,planning:{ceiling_cents:23000,reserve_percent:10}},
  {total_cents:5000,planning:{ceiling_cents:null,reserve_percent:5}},
  {total_cents:1000}
 ]);
 assert.equal(x.events,3);
 assert.equal(x.withCeiling,1);
 assert.equal(x.overCeiling,1);
 assert.equal(x.reserveCents,2450);
 assert.equal(x.projectedCents,30450);
 assert.equal(x.overCeilingCents,1200);
});
test("invalid reserve percentages fail validation",()=>{
 for(const bad of [-1,51,2.5,NaN])assert.throws(()=>budgetForecast(100,null,bad),/Invalid/);
});
