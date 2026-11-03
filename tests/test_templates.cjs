const {test}=require("node:test");const assert=require("node:assert/strict");
const {validTemplateDate,templatePreview,templateRequestPayload}=require("../static/templates.js");
const sample={key:"volleyball",expenses:[{title:"Court",cents:16000,category:"venue"},
 {title:"Equipment",cents:2500,category:"equipment"}],
 tasks:["Check court","Confirm attendance"]};
test("exact-cent preview and opt-out choices",()=>{
 const original=JSON.stringify(sample);
 assert.deepEqual(templatePreview(sample),{expenses:sample.expenses,tasks:sample.tasks,
  estimatedCents:18500,expenseCount:2,taskCount:2});
 assert.equal(templatePreview(sample,false,true).estimatedCents,0);
 assert.equal(templatePreview(sample,true,false).taskCount,0);
 assert.equal(templatePreview(sample,false,false).expenseCount,0);
 assert.equal(JSON.stringify(sample),original);
});
test("request body is trimmed and has a repeatable idempotency key",()=>{
 const key="a00bc123-cdef-4d00-8da0-0123456789ab";
 const p=templateRequestPayload("volleyball","  Friends volleyball  ","2026-11-15",true,false,key);
 assert.deepEqual(p,{key:"volleyball",body:{name:"Friends volleyball",date:"2026-11-15",
  include_expenses:true,include_tasks:false,request_key:key}});
});
test("real calendar validation blocks invalid date and incomplete name",()=>{
 assert.equal(validTemplateDate("2026-02-30"),false);
 assert.equal(validTemplateDate("2028-02-29"),true);
 assert.equal(validTemplateDate("2026-13-01"),false);
 assert.throws(()=>templateRequestPayload("volleyball"," A ","2026-11-15",true,true,
  "a00bc123-cdef-4d00-8da0-0123456789ab"),/Check/);
 assert.throws(()=>templateRequestPayload("volleyball","Fine name","2026-11-99",true,true,
  "a00bc123-cdef-4d00-8da0-0123456789ab"),/Check/);
});
test("fake template costs fail closed",()=>{
 assert.throws(()=>templatePreview({expenses:[{cents:Infinity}],tasks:[]}),/invalid cost/);
 assert.throws(()=>templatePreview({expenses:[{cents:-100}],tasks:[]}),/invalid cost/);
 assert.throws(()=>templatePreview(null),/Invalid/);
});
