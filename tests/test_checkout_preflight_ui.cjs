"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const start=html.indexOf("const checkoutPreflightInFlight=new Set();");
const end=html.indexOf("async function verifyPayPalOrder(",start);
assert.ok(start>0 && end>start,"Missing checkout-readiness UI handler");
const code=html.slice(start,end);

function harness({report,confirm=true,postResponse={
 mode:"PAYPAL_SANDBOX",
 approval_url:"https://www.sandbox.paypal.com/checkoutnow?token=TEST"
},requestError=null,selectedEvent=1,canManageSandbox=true}={}){
 const elements=new Map(),calls=[],messages=[],redirects=[];
 const model={event:selectedEvent};
 const nodes=[];
 function el(id){
  if(!elements.has(id))elements.set(id,{
   id,textContent:"",children:[],
   replaceChildren(){this.children=[];this.textContent="" },
   appendChild(x){this.children.push(x)}
  });
  return elements.get(id);
 }
 const doc={createElement:tag=>{
  const value={tag,textContent:"",children:[],appendChild(child){this.children.push(child)}};
  nodes.push(value);
  return value;
 }};
 const context=vm.createContext({
  state:{sandbox_order_actions_allowed:canManageSandbox},
  el,document:doc,
  request:async url=>{
   calls.push(["GET",url]);
   if(requestError)throw Error(requestError);
   return report;
  },
  post:async url=>{calls.push(["POST",url]);return postResponse},
  window:{confirm:()=>{calls.push(["CONFIRM"]);return confirm},
   location:{assign:url=>redirects.push(url)}},
  event:()=>model.event===null?null:{id:model.event},
  money:cents=>"$"+(cents/100).toFixed(2),
  notice:(...args)=>messages.push(args),
  URL,Set,Number,String,Error
 });
 vm.runInContext(code,context,{timeout:2000});
 return {
  inspect:vm.runInContext("checkCheckoutReadiness",context),
  checkout:vm.runInContext("paypalCheckout",context),
  el,calls,redirects,messages,model,nodes
 };
}
const ready={
 mode:"PAYPAL_SANDBOX",can_create_order:true,amount_cents:1100,
 blockers:[],notice:"Read-only local preflight, not provider availability."
};

test("contributions expose an accessible read-only eligibility panel",()=>{
 assert.match(html,/id="checkout-readiness-status"[^>]*role="status"/);
 assert.match(html,/id="checkout-readiness-details"/);
 assert.match(html,/Check readiness/);
 assert.match(html,/onclick="checkCheckoutReadiness\(/);
 assert.match(html,/Read-only preflight/);
});

test("blocked checkout explains local prerequisites and never sends PayPal POST",async()=>{
 const h=harness({report:{
  ...ready,can_create_order:false,
  blockers:[
   {code:"approval_required",explanation:"Obtain participant approval."},
   {code:"allocation_inconsistent",explanation:"Review the exact-cent budget."}
  ]
 }});
 await h.inspect(4);
 assert.deepEqual(h.calls,[["GET","/api/paypal/checkout-readiness/1/4"]]);
 assert.match(h.el("checkout-readiness-status").textContent,/2 prerequisite/);
 assert.equal(h.el("checkout-readiness-details").children[0].children.length,2);
 assert.equal(h.el("checkout-readiness-details").children[0].children[0].textContent,
  "Obtain participant approval.");
 await h.checkout(4);
 assert.equal(h.calls.filter(x=>x[0]==="POST").length,0);
 assert.deepEqual(h.redirects,[]);
});

test("readiness flag false with empty blocker list also fails closed",async()=>{
 const h=harness({report:{...ready,can_create_order:false}});
 await h.checkout(4);
 assert.equal(h.calls.some(x=>x[0]==="POST"),false);
 assert.equal(h.redirects.length,0);
});

test("eligible checkout requires confirmation, then a single Sandbox order POST",async()=>{
 const h=harness({report:ready});
 await h.inspect(8);
 assert.deepEqual(h.calls,[["GET","/api/paypal/checkout-readiness/1/8"]]);
 assert.match(h.el("checkout-readiness-status").textContent,/Locally eligible/);
 await h.checkout(8);
 assert.deepEqual(h.calls.slice(1),[
  ["GET","/api/paypal/checkout-readiness/1/8"],
  ["CONFIRM"],
  ["POST","/api/paypal/orders/1/8"]
 ]);
 assert.deepEqual(h.redirects,["https://www.sandbox.paypal.com/checkoutnow?token=TEST"]);
});

test("declining confirmation never submits a sandbox order",async()=>{
 const h=harness({report:ready,confirm:false});
 await h.checkout(9);
 assert.equal(h.calls.filter(x=>x[0]==="POST").length,0);
 assert.equal(h.redirects.length,0);
});

test("unsafe redirect is rejected after order attempt and must not be followed",async()=>{
 for(const url of [
  "https://not-paypal.example/test",
  "https://sandbox.paypal.com.attacker.example/checkout",
  "http://www.sandbox.paypal.com/checkout",
  "javascript:alert(1)"
 ]){
  const h=harness({report:ready,postResponse:{
   mode:"PAYPAL_SANDBOX",approval_url:url
  }});
  await h.checkout(5);
  assert.equal(h.redirects.length,0,url);
  assert.equal(h.calls.filter(x=>x[0]==="POST").length,1,url);
  assert.match(h.el("checkout-readiness-status").textContent,/Invalid PayPal Sandbox redirect/,url);
 }
});

test("preflight failure and stale event changes never trigger payment POST",async()=>{
 const h=harness({requestError:"Server unavailable"});
 await h.checkout(5);
 assert.equal(h.redirects.length,0);
 assert.equal(h.calls.filter(x=>x[0]==="POST").length,0);
 assert.match(h.el("checkout-readiness-status").textContent,/Server unavailable/);
 const stale=harness({report:ready});
 stale.model.event=9;
 await stale.checkout(2);
 assert.deepEqual(stale.calls,[["GET","/api/paypal/checkout-readiness/9/2"],["CONFIRM"],["POST","/api/paypal/orders/9/2"]]);
});

test("existing-order warning directs organizer to recovery, without retrying",async()=>{
 const h=harness({report:{...ready,can_create_order:false,blockers:[
  {code:"existing_order",explanation:"Inspect the existing order."}
 ]}});
 await h.checkout(2);
 assert.equal(h.calls.some(x=>x[0]==="POST"),false);
 assert.match(h.messages[0][0],/Never retry order creation/);
});

test("server-supplied messages are displayed with textContent not unsafe HTML",async()=>{
 const malicious='<img src=x onerror=alert(1)>';
 const h=harness({report:{...ready,can_create_order:false,
  blockers:[{code:"approval_required",explanation:malicious}]}});
 await h.inspect(1);
 assert.equal(h.el("checkout-readiness-details").children[0].children[0].textContent,
  malicious);
 assert.doesNotMatch(code,/innerHTML/);
});

test("judge UI cannot initiate provider order even if local preflight looks eligible",async()=>{
 const judge=harness({report:ready,canManageSandbox:false});
 await judge.checkout(8);
 assert.equal(judge.calls.length,0);
 assert.equal(judge.redirects.length,0);
 assert.match(judge.messages[0][0],/Judge access cannot create PayPal Sandbox/);
 // Read-only local diagnostics remain usable for judge sessions.
 await judge.inspect(8);
 assert.deepEqual(judge.calls,[["GET","/api/paypal/checkout-readiness/1/8"]]);
});
