"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
function between(a,b){
 const start=html.indexOf(a),end=html.indexOf(b,start);
 assert.ok(start>=0&&end>start,"Expected protected UI fragment");
 return html.slice(start,end);
}
const roleStart=between("function render(){"," let events=state.events");
const roleBody=roleStart.slice("function render(){".length);
const statusFunction=between("async function verifyPayPalOrder(id){","async function paymentReturn()");
const exportFunction=between("async function downloadReconciliationManifest(){",
                             "async function compareLocalReconciliationFiles()");

function renderRole(canManage){
 const els=new Map();
 const el=id=>{
  if(!els.has(id))els.set(id,{style:{display:"none"},disabled:false,textContent:""});
  return els.get(id);
 };
 const context=vm.createContext({
  state:{sandbox_order_actions_allowed:canManage},
  el
 });
 vm.runInContext("function rolePart(){"+roleBody+"}\nrolePart()",context,{timeout:2000});
 return {el};
}

const judgeAccessFunction=between("async function checkJudgeAccess(){","async function checkReadiness(){");

function judgeAccessHarness(canManage,response){
 const elements=new Map(),calls=[];
 const el=id=>{
  if(!elements.has(id))elements.set(id,{style:{display:"none"},textContent:"",disabled:false});
  return elements.get(id);
 };
 const context=vm.createContext({
  state:{sandbox_order_actions_allowed:canManage},
  el,request:async path=>{calls.push(path);return response;},
  Error
 });
 vm.runInContext(judgeAccessFunction,context,{timeout:2000});
 const check=vm.runInContext("checkJudgeAccess",context);
 return {el,calls,check};
}

test("judge workspace displays a clear role warning and disables manifest export",()=>{
 assert.match(html,/id="sandbox-role-banner"[^>]*role="status"/);
 const judge=renderRole(false);
 assert.equal(judge.el("sandbox-role-banner").style.display,"block");
 assert.match(judge.el("sandbox-role-banner").textContent,/Judge testing mode/);
 assert.match(judge.el("sandbox-role-banner").textContent,/organizer credentials/);
 assert.equal(judge.el("recovery-export").disabled,true);
 const owner=renderRole(true);
 assert.equal(owner.el("sandbox-role-banner").style.display,"none");
 assert.equal(owner.el("recovery-export").disabled,false);
});

test("judge-side order check cannot call status GET/capture even with known order",async()=>{
 const calls=[],messages=[];
 const context=vm.createContext({
  state:{sandbox_order_actions_allowed:false},
  notice:(msg,err)=>messages.push([msg,err]),
  post:async(...args)=>{calls.push(args);throw Error("Forbidden provider call")},
  load:async()=>{throw Error("Should not refresh after blocked call")},
  window:{confirm:()=>{throw Error("No confirm allowed")}},
  encodeURIComponent,Error
 });
 vm.runInContext(statusFunction,context,{timeout:2000});
 const verify=vm.runInContext("verifyPayPalOrder",context);
 await verify("SANDBOX-KNOWN-ORDER-123");
 assert.equal(calls.length,0);
 assert.match(messages[0][0],/Only the organizer may reconcile or capture/);
 assert.equal(messages[0][1],true);
});

test("private recovery export is not fetched in a judge session",async()=>{
 const requests=[],messages=[];
 const context=vm.createContext({
  state:{sandbox_order_actions_allowed:false},
  el:()=>({disabled:false}),
  notice:(msg,err)=>messages.push([msg,err]),
  window:{confirm:()=>{throw Error("Should not ask judge to export")}},
  request:async url=>{requests.push(url);return {}},
  Error
 });
 vm.runInContext(exportFunction,context,{timeout:2000});
 const download=vm.runInContext("downloadReconciliationManifest",context);
 await download();
 assert.equal(requests.length,0);
 assert.match(messages[0][0],/organizer credentials/);
});

test("judge role suppresses PayPal order/capture controls in transaction and recovery tables",()=>{
 assert.match(html,/state\.sandbox_order_actions_allowed!==false&&p\.status!==["']completed["']/);
 assert.match(html,/allowed&&state\.sandbox_order_actions_allowed!==false/);
 assert.match(html,/disabled title='Organizer credentials required'/);
 assert.match(html,/Organizer review required/);
});


test("judge expiry configuration check is owner only in UI and does not call private endpoint for judge",async()=>{
 const h=judgeAccessHarness(false,{ready_for_judging:true,mode:"READ_ONLY_JUDGE_CONFIGURATION_CHECK",problems:[]});
 await h.check();
 assert.deepEqual(h.calls,[]);
 assert.match(h.el("judge-access-status").textContent,/Only the organizer/);
 assert.match(html,/id="judge-access-check"/);
 assert.match(html,/id="judge-access-status"[^>]*role="status"/);
 const judge=renderRole(false);
 assert.equal(judge.el("judge-access-tools").style.display,"none");
 const owner=renderRole(true);
 assert.equal(owner.el("judge-access-tools").style.display,"block");
});

test("owner sees truthful judge expiry coverage without seeing credentials",async()=>{
 const h=judgeAccessHarness(true,{
  mode:"READ_ONLY_JUDGE_CONFIGURATION_CHECK",
  ready_for_judging:true,problems:[],
  judging_ends_at_utc:"2026-12-15T16:00:00Z",
  sandbox_actions_allowed_for_judges:false
 });
 await h.check();
 assert.deepEqual(h.calls,["/api/judge-access-readiness"]);
 assert.match(h.el("judge-access-status").textContent,/covers the published judging period/);
 assert.match(h.el("judge-access-status").textContent,/incognito browser/);
 assert.match(h.el("judge-access-status").textContent,/cannot initiate PayPal Sandbox/);
 assert.equal(h.el("judge-access-check").disabled,false);
 assert.doesNotMatch(h.el("judge-access-status").textContent,/username|password|Bearer/);
});

test("unsafe judge expiry reports actionable problems without leaking server data",async()=>{
 const h=judgeAccessHarness(true,{
  mode:"READ_ONLY_JUDGE_CONFIGURATION_CHECK",
  ready_for_judging:false,
  problems:["judge_login_disabled","judge_login_expires_during_judging","UNKNOWN_CODE"]
 });
 await h.check();
 assert.match(h.el("judge-access-status").textContent,/NOT READY/);
 assert.match(h.el("judge-access-status").textContent,/Enable the separate judge login/);
 assert.match(h.el("judge-access-status").textContent,/15 December 2026/);
 assert.match(h.el("judge-access-status").textContent,/Review access configuration/);
 assert.equal(h.el("judge-access-check").disabled,false);
});

test("malformed owner access response fails closed without a login claim",async()=>{
 const h=judgeAccessHarness(true,{ready_for_judging:true});
 await h.check();
 assert.match(h.el("judge-access-status").textContent,/Could not inspect/);
 assert.equal(h.el("judge-access-check").disabled,false);
});
