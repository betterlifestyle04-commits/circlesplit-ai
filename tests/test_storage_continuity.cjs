"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const continuity=require("../static/storage_continuity.js");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const BEFORE="11111111-111";
const AFTER="22222222-222";
function readiness(epoch=BEFORE,captures=0,webhooks=0) {
 return {mode:"sandbox-only",storage_epoch:epoch,
  current_store_verified_captures:captures,
  current_store_webhook_events:webhooks,
  ai_key_present:false,paypal_key_pair_present:false,
  private_token:"NEVER-PERSIST-THIS"};
}
function storage() {
 const items=new Map();
 return {
  getItem:k=>items.has(k)?items.get(k):null,
  setItem:(k,v)=>items.set(k,v),
  items
 };
}
function elements() {
 const map=new Map();
 for(const id of ["continuity-status","continuity-alert","continuity-details",
                  "continuity-check","continuity-acknowledge"]) {
  map.set(id,{
   textContent:"",style:{display:"none"},disabled:id==="continuity-acknowledge",
   handlers:{},addEventListener(name,fn){this.handlers[name]=fn},
   async click(){return this.handlers.click?.()}
  });
 }
 return {doc:{getElementById:id=>map.get(id)},get:id=>map.get(id)};
}
function harness({initial,saveStore=storage(),remote=initial,confirmation=true}={}) {
 const els=elements(),requestCalls=[],confirmCalls=[];
 let current=remote;
 let error=null;
 const fetchReadiness=async()=> {
  requestCalls.push("GET /api/judge-readiness");
  if(error)throw Error(error);
  return current;
 };
 const monitor=continuity.setup(
  els.doc,saveStore,fetchReadiness,
  reason=>{confirmCalls.push(reason);return confirmation}
 );
 return {monitor,els,saveStore,requestCalls,confirmCalls,
         setRemote:d=>current=d,fail:e=>error=e,clearError:()=>error=null};
}

test("checkpoint schema accepts only anonymous, bounded local dataset evidence",()=>{
 const raw=readiness(BEFORE,4,5);
 const marker=continuity.snapshot(raw,"2026-11-05T12:00:00.000Z");
 assert.deepEqual(marker,{
  version:1,epoch:BEFORE,captures:4,webhooks:5,
  observed_at:"2026-11-05T12:00:00.000Z"
 });
 assert.equal(JSON.stringify(marker).includes("NEVER-PERSIST-THIS"),false);
 assert.equal(Object.keys(marker).length,5);
 for(const invalid of [
  {...raw,storage_epoch:"not-an-epoch"},
  {...raw,storage_epoch:""},
  {...raw,mode:"live"},
  {...raw,current_store_verified_captures:-1},
  {...raw,current_store_webhook_events:"5"},
  {...raw,current_store_verified_captures:1.5},
  {...raw,current_store_verified_captures:Number.MAX_SAFE_INTEGER},
  null
 ])assert.throws(()=>continuity.snapshot(invalid),/incomplete/);
});

test("first observation stores only bounded marker; normal growth updates high-water counts",()=>{
 const h=harness();
 assert.equal(h.monitor.observe(readiness(BEFORE,3,4)).kind,"first");
 const one=continuity.load(h.saveStore);
 assert.equal(one.state,"stored");
 assert.equal(one.value.epoch,BEFORE);
 assert.equal(one.value.captures,3);
 assert.equal(h.els.get("continuity-alert").style.display,"none");
 assert.equal(h.els.get("continuity-acknowledge").disabled,true);
 assert.equal(h.monitor.observe(readiness(BEFORE,5,9)).kind,"consistent");
 assert.equal(continuity.load(h.saveStore).value.captures,5);
 assert.equal(continuity.load(h.saveStore).value.webhooks,9);
 assert.equal(h.requestCalls.length,0,"Observing existing GET must not create a second request");
 assert.equal(h.saveStore.items.size,1);
});

test("dataset reset warns across tabs while preserving the previous checkpoint",async()=>{
 const h=harness({remote:readiness(AFTER,0,0)});
 h.monitor.observe(readiness(BEFORE,8,5));
 const changed=h.monitor.observe(readiness(AFTER,0,0));
 assert.equal(changed.kind,"new-dataset");
 assert.equal(continuity.load(h.saveStore).value.epoch,BEFORE);
 assert.equal(h.els.get("continuity-alert").style.display,"block");
 assert.match(h.els.get("continuity-alert").textContent,/possible storage reset/i);
 assert.match(h.els.get("continuity-alert").textContent,/inspect the PayPal Sandbox account/);
 assert.equal(h.els.get("continuity-acknowledge").disabled,false);
 await h.monitor.check();
 assert.equal(continuity.load(h.saveStore).value.epoch,BEFORE);
 assert.equal(h.monitor.report().kind,"new-dataset");
});

test("record-count regression is flagged even when dataset ID stays identical",()=>{
 const h=harness();
 h.monitor.observe(readiness(BEFORE,12,22));
 assert.equal(h.monitor.observe(readiness(BEFORE,11,23)).kind,"count-regression");
 assert.equal(continuity.load(h.saveStore).value.captures,12);
 assert.equal(continuity.load(h.saveStore).value.webhooks,22);
 assert.match(h.els.get("continuity-alert").textContent,/data rollback/i);
 assert.match(h.els.get("continuity-status").textContent,/lower/);
});

test("acknowledge requires explicit confirmation and fresh unchanged evidence",async()=>{
 const h=harness({remote:readiness(AFTER,2,1)});
 h.monitor.observe(readiness(BEFORE,9,11));
 h.monitor.observe(readiness(AFTER,2,1));
 await h.monitor.acknowledge();
 assert.equal(h.confirmCalls.length,1);
 assert.match(h.confirmCalls[0],/checking existing PayPal Sandbox orders externally/);
 assert.equal(h.requestCalls.length,1);
 assert.equal(continuity.load(h.saveStore).value.epoch,AFTER);
 assert.equal(h.els.get("continuity-alert").style.display,"none");
 assert.match(h.els.get("continuity-status").textContent,/NOT provider reconciliation/);
 assert.equal(h.els.get("continuity-acknowledge").disabled,true);
});

test("declining confirmation never changes checkpoint",async()=>{
 const h=harness({remote:readiness(AFTER,1,1),confirmation:false});
 h.monitor.observe(readiness(BEFORE,8,3));
 h.monitor.observe(readiness(AFTER,1,1));
 await h.monitor.acknowledge();
 assert.equal(h.requestCalls.length,0);
 assert.equal(continuity.load(h.saveStore).value.epoch,BEFORE);
 assert.equal(h.els.get("continuity-alert").style.display,"block");
});

test("stale acknowledgement cannot erase another newly changed dataset",async()=>{
 const h=harness({remote:readiness("33333333-333",0,0)});
 h.monitor.observe(readiness(BEFORE,5,5));
 h.monitor.observe(readiness(AFTER,0,0));
 await h.monitor.acknowledge();
 assert.equal(continuity.load(h.saveStore).value.epoch,BEFORE);
 assert.equal(h.els.get("continuity-alert").style.display,"block");
 assert.match(h.els.get("continuity-status").textContent,/dataset changed/);
});

test("another browser tab moving the baseline prevents stale acknowledgement",async()=>{
 const store=storage(),h=harness({saveStore:store,remote:readiness(AFTER,0,0)});
 h.monitor.observe(readiness(BEFORE,4,3));
 h.monitor.observe(readiness(AFTER,0,0));
 continuity.save(store,continuity.snapshot(readiness("aaaaaaaa-aaa",10,8)));
 await h.monitor.acknowledge();
 assert.equal(continuity.load(store).value.epoch,"aaaaaaaa-aaa");
 assert.match(h.els.get("continuity-status").textContent,/another tab/);
});

test("corrupted browser checkpoint never gets silently replaced or treated as healthy",async()=>{
 const store=storage();
 store.items.set(continuity.KEY,JSON.stringify({
  version:1,epoch:BEFORE,captures:"3",webhooks:2,
  observed_at:"2026-11-05T12:00:00.000Z",person_name:"Alex"
 }));
 const h=harness({saveStore:store,remote:readiness(AFTER,0,0)});
 assert.equal(h.monitor.observe(readiness(AFTER,0,0)).kind,"invalid");
 assert.equal(h.els.get("continuity-alert").style.display,"block");
 assert.equal(continuity.load(store).state,"invalid");
 await h.monitor.check();
 assert.equal(continuity.load(store).state,"invalid");
});

test("disabled browser storage fails safely instead of pretending continuity is monitored",()=>{
 const denied={getItem(){throw Error("SecurityError")},setItem(){throw Error("SecurityError")}};
 const h=harness({saveStore:denied});
 assert.equal(h.monitor.observe(readiness(BEFORE,0,0)).kind,"unavailable");
 assert.match(h.els.get("continuity-status").textContent,/unavailable/);
 assert.equal(h.els.get("continuity-acknowledge").disabled,true);
 assert.equal(h.els.get("continuity-alert").style.display,"none");
 const h2=harness({saveStore:()=>{throw Error("SecurityError")}});
 assert.equal(h2.monitor.observe(readiness(BEFORE,0,0)).kind,"unavailable");
});

test("network failure preserves reset warning and never writes a baseline",async()=>{
 const h=harness({remote:readiness(AFTER,0,0)});
 h.monitor.observe(readiness(BEFORE,5,4));
 h.monitor.observe(readiness(AFTER,0,0));
 h.fail("Network error");
 await h.monitor.check();
 assert.match(h.els.get("continuity-status").textContent,/unavailable/);
 assert.equal(h.els.get("continuity-alert").style.display,"block");
 assert.equal(continuity.load(h.saveStore).value.epoch,BEFORE);
 assert.equal(h.els.get("continuity-acknowledge").disabled,true);
});

test("workspace layout exposes monitor globally and only requests the existing private status API",()=>{
 assert.match(html,/id="continuity-alert"[^>]*role="alert"/);
 assert.match(html,/id="continuity-status"[^>]*role="status"/);
 assert.match(html,/id="continuity-check"/);
 assert.match(html,/id="continuity-acknowledge" disabled/);
 assert.match(html,/src="\/static\/storage_continuity\.js"/);
 assert.match(html,/CircleSplitContinuity\.setup/);
 assert.match(html,/continuityMonitor\.observe\(d\)/);
 assert.match(html,/request\("\/api\/judge-readiness"\)/);
 assert.doesNotMatch(fs.readFileSync(path.join(__dirname,"../static/storage_continuity.js"),"utf8"),
  /\/api\/paypal\/capture|\/api\/paypal\/orders|fetch\(/);
});
