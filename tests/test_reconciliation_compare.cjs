"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const {createHash,webcrypto}=require("node:crypto");
const cmp=require("../static/reconciliation_compare.js");

const EPOCH1="11111111-1111-4111-a111-111111111111";
const EPOCH2="22222222-2222-4222-a222-222222222222";
const earlier="2026-11-04T20:00:00+00:00";
const later="2026-11-04T21:00:00+00:00";
function row(payment_id,overrides={}){
 return {
  payment_id,event_id:2,person_id:3,
  event_name:"Bølge & bølger 🌊",participant_name:"Alex",
  amount_cents:1100,status:"completed",
  created_at:earlier,
  paypal_order_id:"TEST-ORDER-"+payment_id,
  paypal_capture_id:"TEST-CAP-"+payment_id,
  ...overrides
 };
}
function manifest(rows,{epoch=EPOCH1,date=earlier}={}){
 return {app:"CircleSplit AI",
  kind:"paypal-sandbox-reconciliation-manifest",
  schema_version:1,mode:"PAYPAL_SANDBOX",currency:"USD",
  importable:false,generated_at:date,
  storage_epoch:epoch,storage_created_at:earlier,
  record_count:rows.length,records_sha256:createHash("sha256").update(
   cmp.canonical(rows),"utf8").digest("hex"),records:rows,
  limitations:"Local only; not a PayPal settlement record."
 };
}

test("canonical encoding agrees with Python's actual UTF-8 sorted-key export",async()=>{
 const data=[row(1,{paypal_order_id:"TEST-ORDER-1",paypal_capture_id:"TEST-CAP-1"})];
 const snapshot=manifest(data);
 assert.equal(snapshot.records_sha256,
  "dc1b60e6e78f68fcdd24735f6b500d5904d33a497460e47c3a3be061a6222483");
 assert.equal((await cmp.verifyManifest(snapshot,webcrypto.subtle)).record_count,1);
});

test("the browser verifies digests before trusting snapshots",async()=>{
 const snapshot=manifest([row(1)]);
 await cmp.verifyManifest(snapshot,webcrypto.subtle);
 snapshot.records[0].amount_cents++;
 await assert.rejects(cmp.verifyManifest(snapshot,webcrypto.subtle),
  /digest does not match/);
 await assert.rejects(cmp.verifyManifest(snapshot,null),/Secure browser SHA-256/);
});

test("invalid or ambiguous manifests are rejected safely",()=>{
 const one=row(1);
 const base=manifest([one]);
 for(const invalid of [
  {...base,kind:"planning-backup"},
  {...base,mode:"LIVE"},
  {...base,importable:true},
  {...base,record_count:0},
  {...base,storage_epoch:"fake"},
  {...base,records_sha256:"x"},
  manifest([one,one]),
  manifest([one,row(2,{paypal_order_id:one.paypal_order_id})]),
  manifest([row(1,{evil_script:"any"})]),
  manifest([row(1,{amount_cents:"$11"})]),
 ]){
  assert.throws(()=>cmp.validateManifest(invalid));
 }
});

test("same database compares stable IDs and ordinary payment progression",()=>{
 const start=manifest([
  row(1,{status:"creating",paypal_order_id:null,paypal_capture_id:null}),
  row(2,{status:"created",paypal_capture_id:null}),
  row(3)
 ]);
 const finish=manifest([
  row(1,{status:"created",paypal_capture_id:null}),
  row(2),
  row(3),
  row(4,{status:"creating",paypal_order_id:null,paypal_capture_id:null})
 ],{date:later});
 const result=cmp.compareManifests(start,finish);
 assert.equal(result.scope,"same-database");
 assert.equal(result.matched,3);
 assert.equal(result.missing,0);
 assert.equal(result.added,1);
 assert.equal(result.statusChanges,2);
 assert.equal(result.newlyCompleted,1);
 assert.equal(result.captureChanges,0);
 assert.equal(result.concerning,0);
 assert.equal(result.databaseChanged,false);
});

test("same database identifies disappearing rows, amount edits and capture regression",()=>{
 const start=manifest([row(1),row(2),row(3)]);
 const finish=manifest([
  row(1,{status:"created",paypal_capture_id:null,amount_cents:1400}),
  row(2,{paypal_capture_id:"DIFFERENT-CAPTURE",
         event_id:5,paypal_order_id:"OTHER-ORDER"}),
  row(4)
 ],{date:later});
 const result=cmp.compareManifests(start,finish);
 assert.equal(result.missing,1);
 assert.equal(result.added,1);
 assert.equal(result.completedRegressions,1);
 assert.equal(result.captureChanges,2);
 assert.equal(result.amountChanges,1);
 assert.equal(result.orderChanges,1);
 assert.equal(result.referenceChanges,1);
 assert.equal(result.concerning,7);
});

test("database reset never matches reused local IDs to unrelated sandbox orders",()=>{
 const start=manifest([
  row(1,{status:"completed",paypal_order_id:"BEFORE-ORDER",
         paypal_capture_id:"BEFORE-CAPTURE"}),
  row(2,{status:"creating",paypal_order_id:null,paypal_capture_id:null})
 ]);
 const finish=manifest([
  row(1,{status:"completed",paypal_order_id:"NEW-ORDER",
         paypal_capture_id:"NEW-CAPTURE"}),
  row(2,{status:"created",paypal_order_id:"BEFORE-ORDER",
         paypal_capture_id:null})
 ],{epoch:EPOCH2,date:later});
 const result=cmp.compareManifests(start,finish);
 assert.equal(result.scope,"database-changed");
 assert.equal(result.databaseChanged,true);
 assert.equal(result.matched,1); // Match provider order, NOT reused payment id.
 assert.equal(result.missing,0);
 assert.equal(result.added,1);
 assert.equal(result.priorUntrackable,1);
 assert.equal(result.followupUntrackable,0);
 assert.equal(result.completedRegressions,1);
 assert.equal(result.captureChanges,1);
 assert.equal(result.referenceChanges,0);
 assert.match(result.warnings.join(" "),/database reset/);
});

test("cross-reset missing known PayPal order cannot be mistaken for no payment",()=>{
 const start=manifest([row(1),row(2)]);
 const finish=manifest([row(1,{paypal_order_id:"OTHER-ORDER-1"})],
  {epoch:EPOCH2,date:later});
 const result=cmp.compareManifests(start,finish);
 assert.equal(result.missing,2);
 assert.equal(result.matched,0);
 assert.equal(result.added,1);
 assert.match(result.warnings.join(" "),/never retry a charge/);
});

test("reversed files are rejected instead of producing misleading comparisons",()=>{
 const start=manifest([row(1)],{date:later});
 const finish=manifest([row(1)],{date:earlier});
 assert.throws(()=>cmp.compareManifests(start,finish),/baseline file is newer/);
});

test("local file reader enforces size limits and validates JSON without provider I/O",async()=>{
 const contents=JSON.stringify(manifest([row(1)]));
 const file={size:Buffer.byteLength(contents),text:async()=>contents};
 const data=await cmp.readSnapshot(file,webcrypto.subtle);
 assert.equal(data.record_count,1);
 await assert.rejects(cmp.readSnapshot(null,webcrypto.subtle),/Select both/);
 await assert.rejects(cmp.readSnapshot({
  size:cmp.MAX_FILE_BYTES+1,text:async()=>{throw Error("Should not read")}
 },webcrypto.subtle),/under 8 MB/);
 await assert.rejects(cmp.readSnapshot({size:3,text:async()=>"{x"},webcrypto.subtle),
  /Unable to read snapshot JSON/);
});
