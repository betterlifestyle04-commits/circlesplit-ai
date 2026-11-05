"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const start=html.indexOf("async function paymentReturn(){");
const end=html.indexOf("async function downloadPlanningBackup",start);
assert.ok(start>0&&end>start,"PayPal Sandbox return handler missing");
const script=html.slice(start,end);

function harness(search){
 const calls=[];
 const context=vm.createContext({
  window:{location:{search}},
  location:{pathname:"/workspace"},
  history:{replaceState(...args){calls.push(["strip",...args])}},
  switchTab:value=>calls.push(["tab",value]),
  notice:(...args)=>calls.push(["notice",...args]),
  verifyPayPalOrder:async id=>calls.push(["checkExisting",id]),
  post:async()=>{calls.push(["unsafeCapture"]);throw Error("Unsafe direct capture")},
  run:async()=>{calls.push(["unsafeRun"]);throw Error("Unsafe direct capture")},
  URLSearchParams
 });
 vm.runInContext(script,context,{timeout:2000});
 return {calls,execute:vm.runInContext("paymentReturn",context)};
}

test("approved buyer redirect only checks the EXISTING order, never directly captures",async()=>{
 const h=harness("?payment=return&token=SANDBOX-ORDER-123");
 await h.execute();
 assert.deepEqual(h.calls.slice(0,2),[
  ["strip",null,"","/workspace"],["tab","activity"]
 ]);
 assert(h.calls.some(c=>c[0]==="notice"&&c[1].includes("does not prove a capture")));
 assert.deepEqual(h.calls.filter(c=>c[0]==="checkExisting"),[["checkExisting","SANDBOX-ORDER-123"]]);
 assert.equal(h.calls.some(c=>c[0]==="unsafeCapture"||c[0]==="unsafeRun"),false);
});

test("cancelled buyer return strips URL token and never calls provider",async()=>{
 const h=harness("?payment=cancelled&token=ORDER-12345");
 await h.execute();
 assert.deepEqual(h.calls[0],["strip",null,"","/workspace"]);
 assert(h.calls.some(c=>c[0]==="notice"&&c[1].includes("never create another")));
 assert.equal(h.calls.filter(c=>c[0]==="checkExisting").length,0);
});

test("missing or malicious provider order references cannot trigger check/capture",async()=>{
 for(const url of [
  "?payment=return",
  "?payment=return&token=tiny",
  "?payment=return&token=%3Cscript%3Ealert(1)%3C/script%3E",
  "?payment=return&token=ORDER_123",
  "?payment=return&token=EXCESSIVELY-LONG-"+("X".repeat(100)),
 ]){
  const h=harness(url);
  await h.execute();
  assert.equal(h.calls.filter(c=>c[0]==="checkExisting").length,0,url);
  assert.deepEqual(h.calls[0],["strip",null,"","/workspace"],url);
  assert(h.calls.some(c=>c[0]==="notice"&&c[1].includes("no capture was sent")),url);
 }
});

test("unrelated query params do not start any payment or navigation",async()=>{
 const h=harness("?payment=unknown&token=SANDBOX-ORDER-123");
 await h.execute();
 assert.deepEqual(h.calls,[]);
});

test("buyer return implementation only performs status reconciliation",()=>{
 assert.match(script,/await verifyPayPalOrder\(orderId\)/);
 assert.doesNotMatch(script,/\/api\/paypal\/capture/);
 assert.doesNotMatch(script,/await post\(/);
 assert.match(html,/PayPal Sandbox/);
});
