const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length,1,"Expected protected workspace's single inline script");
const inline=scripts[0][1];
const begin=inline.indexOf("let recoveryOffset=0,recoveryLimit=50;");
const end=inline.indexOf("async function paypalCheckout",begin);
assert.ok(begin>=0&&end>begin,"Recovery page component was not found");
const code=inline.slice(begin,end);

function harness(responses){
 const elements=new Map(),requests=[];
 const el=id=>{
  if(!elements.has(id))elements.set(id,{innerHTML:"",textContent:"",disabled:false});
  return elements.get(id);
 };
 const context=vm.createContext({
  el,
  request:async url=>{
   requests.push(url);
   assert.ok(responses.length>0,"Unexpected recovery request");
   return responses.shift();
  },
  safe:value=>String(value),
  money:value=>"$"+(value/100).toFixed(2),
  notice:()=>{},
  Number,Math,
 });
 vm.runInContext(code,context,{timeout:2000});
 return {context,el,requests,load:vm.runInContext("loadRecovery",context)};
}

function page(offset,nextOffset,items){
 return {
  mode:"PAYPAL_SANDBOX",total_records:3,returned:items.length,offset,limit:2,
  attention_count:1,summary:{creating:1,created:0,capturing:0,completed:2,other:0},
  next_offset:nextOffset,is_truncated:nextOffset!==null,
  items:items.map((n)=>({id:n,order_id:n===1?null:"RECOVERY-ORDER-"+n,
    event_name:"Test event",person_name:"Fictional tester",amount_cents:1100,
    status:n===1?"creating":"completed",action:n===1?"manual_review":"none",
    explanation:n===1?"Do not retry":"No further action"})),
 };
}

test("recovery UI displays full-ledger counts and pages without hiding unresolved rows",async()=>{
 const h=harness([page(0,2,[1,3]),page(2,null,[2])]);
 await h.load();
 assert.equal(h.requests[0],"/api/paypal/recovery?limit=50&offset=0");
 assert.match(h.el("recovery-summary").innerHTML,/Needs investigation: 1/);
 assert.match(h.el("recovery-rows").innerHTML,/Manual review required/);
 assert.match(h.el("recovery-page").textContent,/Showing 1–2 of 3/);
 assert.equal(h.el("recovery-prev").disabled,true);
 assert.equal(h.el("recovery-next").disabled,false);
 await h.load(2);
 assert.equal(h.requests[1],"/api/paypal/recovery?limit=2&offset=2");
 assert.match(h.el("recovery-page").textContent,/Showing 3–3 of 3/);
 assert.equal(h.el("recovery-prev").disabled,false);
 assert.equal(h.el("recovery-next").disabled,true);
 assert.match(h.el("recovery-summary").innerHTML,/Creating: 1/);
});

test("recovery UI refuses invalid offset values",async()=>{
 const h=harness([page(0,null,[])]);
 await h.load(-99);
 assert.equal(h.requests[0],"/api/paypal/recovery?limit=50&offset=0");
});

test("recovery controls are accessible and pagination keeps sandbox guardrails visible",()=>{
 assert.match(html,/id="recovery-page" role="status"/);
 assert.match(html,/id="recovery-prev"/);
 assert.match(html,/id="recovery-next"/);
 assert.match(html,/No automatic retries, no second capture attempts/);
 assert.match(code,/next_offset===null/);
});
