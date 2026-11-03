const {test}=require("node:test"),assert=require("node:assert/strict");
const {CATEGORY_KEYS,normalizeCategory,categoryOptions,budgetCategories,allBudgetCategories}=require("../static/categories.js");
test("all six supported categories have bounded options",()=>{
 assert.deepEqual(CATEGORY_KEYS,["venue","equipment","food","travel","services","other"]);
 assert.equal(normalizeCategory("unknown"),"other");
 const html=categoryOptions("equipment");
 assert.match(html,/<option value="equipment" selected>/);
 assert.ok(!html.includes("alert("));
 assert.equal((html.match(/<option/g)||[]).length,6);
});
test("category totals balance exactly at integer-cent precision",()=>{
 const report=budgetCategories([
  {category:"venue",cents:16001},{category:"equipment",cents:2501},
  {category:"food",cents:3500},{category:"other",cents:1}
 ]);
 assert.equal(report.totalCents,22003);
 assert.equal(report.categories.find(x=>x.key==="venue").cents,16001);
 assert.equal(report.categories.reduce((n,x)=>n+x.cents,0),report.totalCents);
});
test("legacy expenses automatically belong to Other",()=>{
 const d=budgetCategories([{cents:100},{cents:200,category:"bogus"}]);
 assert.equal(d.categories.find(x=>x.key==="other").cents,300);
 assert.equal(d.categories.find(x=>x.key==="other").count,2);
});
test("cross-event report totals agree with individual event totals",()=>{
 const events=[{expenses:[{category:"venue",cents:100}]},
               {expenses:[{category:"venue",cents:200},{category:"travel",cents:30}]}];
 const report=allBudgetCategories(events);
 assert.equal(report.totalCents,330);
 assert.equal(report.categories.find(x=>x.key==="venue").cents,300);
 assert.equal(report.categories.find(x=>x.key==="travel").cents,30);
});
test("invalid expense cents fail closed instead of silently inflating graphs",()=>{
 assert.throws(()=>budgetCategories([{cents:NaN}]),/Invalid expense/);
 assert.throws(()=>budgetCategories([{cents:9.2}]),/Invalid expense/);
 assert.throws(()=>budgetCategories([{cents:-50}]),/Invalid expense/);
 assert.equal(budgetCategories([]).totalCents,0);
});
