"use strict";
/* Browser-only PayPal SANDBOX manifest validation and comparison.
 * This module never performs network I/O, persists uploaded files, or mutates
 * finance state. SHA-256 detects accidental changes, NOT authenticity.
 */
(function(root){
 const KIND="paypal-sandbox-reconciliation-manifest";
 const MAX_RECORDS=10000;
 const MAX_FILE_BYTES=8_000_000;
 const ROW_KEYS=[
  "payment_id","event_id","person_id","event_name","participant_name",
  "amount_cents","status","created_at","paypal_order_id","paypal_capture_id"
 ];
 const ROW_SET=new Set(ROW_KEYS);
 function fail(message){throw new Error(message)}
 function object(value){
  return !!value && typeof value==="object" && !Array.isArray(value);
 }
 function canonical(value){
  if(Array.isArray(value))return "["+value.map(canonical).join(",")+"]";
  if(object(value)){
   const keys=Object.keys(value).sort();
   return "{"+keys.map(k=>JSON.stringify(k)+":"+canonical(value[k])).join(",")+"}";
  }
  if(value===null || typeof value==="string"||typeof value==="boolean")return JSON.stringify(value);
  if(typeof value==="number"&&Number.isSafeInteger(value))return String(value);
  return fail("Manifest contains an unsupported value.");
 }
 function requireInteger(value,label,minimum=0){
  if(!Number.isSafeInteger(value)||value<minimum)fail(label+" must be an integer.");
 }
 function optionalString(value,label,max=180){
  if(value!==null&&(typeof value!=="string"||value.length>max))
   fail(label+" must be short text or null.");
 }
 function validateManifest(manifest){
  if(!object(manifest) || manifest.app!=="CircleSplit AI" ||
     manifest.kind!==KIND || manifest.schema_version!==1 ||
     manifest.mode!=="PAYPAL_SANDBOX" || manifest.currency!=="USD" ||
     manifest.importable!==false || !Array.isArray(manifest.records))
   fail("Not a CircleSplit AI Sandbox reconciliation manifest v1.");
  requireInteger(manifest.record_count,"Record count");
  if(manifest.record_count>MAX_RECORDS ||
     manifest.record_count!==manifest.records.length)
   fail("The manifest is incomplete or exceeds the safe record limit.");
  if(typeof manifest.storage_epoch!=="string" ||
     !/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i.test(manifest.storage_epoch))
   fail("The database incarnation ID is missing or invalid.");
  if(typeof manifest.generated_at!=="string"||manifest.generated_at.length>48||
     !Number.isFinite(Date.parse(manifest.generated_at)))
   fail("The snapshot date is invalid.");
  if(typeof manifest.records_sha256!=="string"||
     !/^[0-9a-f]{64}$/i.test(manifest.records_sha256))
   fail("The manifest digest is missing or invalid.");
  const ids=new Set();
  const orders=new Set();
  for(const row of manifest.records){
   if(!object(row) || Object.keys(row).length!==ROW_KEYS.length ||
      Object.keys(row).some(key=>!ROW_SET.has(key)) ||
      ROW_KEYS.some(key=>!Object.prototype.hasOwnProperty.call(row,key)))
    fail("Manifest contains an unsupported payment record.");
   requireInteger(row.payment_id,"Local payment ID",1);
   requireInteger(row.event_id,"Local event ID",1);
   requireInteger(row.person_id,"Local participant ID",1);
   requireInteger(row.amount_cents,"Payment cents",0);
   optionalString(row.event_name,"Event name",150);
   optionalString(row.participant_name,"Participant name",90);
   optionalString(row.paypal_order_id,"Sandbox order ID",128);
   optionalString(row.paypal_capture_id,"Sandbox capture ID",128);
   if(typeof row.status!=="string"||row.status.length<1||row.status.length>50||
      typeof row.created_at!=="string"||row.created_at.length<8||row.created_at.length>60)
    fail("Manifest contains invalid local payment metadata.");
   if(ids.has(row.payment_id))fail("The snapshot repeats a local payment ID.");
   ids.add(row.payment_id);
   // A single PayPal order must never identify two different local records.
   if(row.paypal_order_id){
    if(orders.has(row.paypal_order_id))fail("The snapshot repeats a PayPal Sandbox order ID.");
    orders.add(row.paypal_order_id);
   }
  }
  return manifest;
 }
 async function verifyManifest(manifest,subtle,TextEncoderClass=TextEncoder){
  validateManifest(manifest);
  if(!subtle||typeof subtle.digest!=="function")
   fail("Secure browser SHA-256 is unavailable. Open this page over HTTPS.");
  const bytes=new TextEncoderClass().encode(canonical(manifest.records));
  const digest=await subtle.digest("SHA-256",bytes);
  const actual=Array.from(new Uint8Array(digest),byte=>byte.toString(16).padStart(2,"0")).join("");
  if(actual!==manifest.records_sha256.toLowerCase())
   fail("Snapshot digest does not match its payment records. Do not rely on this file.");
  return manifest;
 }
 async function readSnapshot(file,subtle,TextEncoderClass=TextEncoder){
  if(!file||typeof file.text!=="function")fail("Select both local JSON snapshots.");
  if(!Number.isSafeInteger(file.size) || file.size<2 || file.size>MAX_FILE_BYTES)
   fail("Each local snapshot must be a JSON file under 8 MB.");
  let data;
  try{data=JSON.parse(await file.text())}
  catch(_){fail("Unable to read snapshot JSON.");}
  return verifyManifest(data,subtle,TextEncoderClass);
 }
 function compareManifests(prior,later){
  validateManifest(prior);
  validateManifest(later);
  const before=Date.parse(prior.generated_at),after=Date.parse(later.generated_at);
  if(before>after)fail("The baseline file is newer than the follow-up. Reverse the selections.");
  const sameEpoch=prior.storage_epoch===later.storage_epoch;
  const idOf=row=>sameEpoch?String(row.payment_id):row.paypal_order_id;
  const oldRows=new Map(),newRows=new Map();
  let oldUntrackable=0,newUntrackable=0;
  for(const row of prior.records){
   const id=idOf(row);
   if(id)oldRows.set(id,row);
   else oldUntrackable++;
  }
  for(const row of later.records){
   const id=idOf(row);
   if(id)newRows.set(id,row);
   else newUntrackable++;
  }
  let matched=0,missing=0,added=0,statusChanges=0,
      completedRegressions=0,captureChanges=0,amountChanges=0,
      orderChanges=0,referenceChanges=0,newlyCompleted=0;
  for(const [id,old] of oldRows){
   const fresh=newRows.get(id);
   if(!fresh){missing++;continue}
   matched++;
   if(old.status!==fresh.status)statusChanges++;
   if(old.status==="completed"&&fresh.status!=="completed")completedRegressions++;
   if(old.status!=="completed"&&fresh.status==="completed")newlyCompleted++;
   if(old.paypal_capture_id && old.paypal_capture_id!==fresh.paypal_capture_id)
    captureChanges++;
   if(old.amount_cents!==fresh.amount_cents)amountChanges++;
   if(sameEpoch){
    if(old.paypal_order_id&&old.paypal_order_id!==fresh.paypal_order_id)orderChanges++;
    if(old.event_id!==fresh.event_id||old.person_id!==fresh.person_id)referenceChanges++;
   }
  }
  for(const id of newRows.keys())if(!oldRows.has(id))added++;
  const concerning=missing+completedRegressions+captureChanges+
                   amountChanges+orderChanges+referenceChanges;
  return {
   scope:sameEpoch?"same-database":"database-changed",
   databaseChanged:!sameEpoch,
   baselineRecords:prior.record_count,
   followupRecords:later.record_count,
   matched,missing,added,priorUntrackable:oldUntrackable,
   followupUntrackable:newUntrackable,statusChanges,newlyCompleted,
   completedRegressions,captureChanges,amountChanges,orderChanges,
   referenceChanges,concerning,
   warnings:[
    ...(sameEpoch?[]:["Database ID changed: local numeric IDs cannot be compared across databases. "+
                      "Only records with a matching PayPal Sandbox order ID were compared."]),
    ...(oldUntrackable?["Some earlier attempts have no known PayPal order ID and cannot be matched "+
                        "across a database reset. They require manual investigation."]:[]),
    ...(concerning?["Some earlier records are absent or have conflicting local values. "+
                     "Check PayPal Sandbox externally; never retry a charge from this comparison."]:[]),
    "Both digests detect accidental record-array changes only, not authenticity or external payment settlement. "+
    "Neither snapshot proves that PayPal captured funds or that lost orders no longer exist."
   ]
  };
 }
 const api={MAX_FILE_BYTES,canonical,validateManifest,verifyManifest,readSnapshot,compareManifests};
 if(typeof module!=="undefined"&&module.exports)module.exports=api;
 else root.CircleSplitReconciliationCompare=api;
})(typeof window!=="undefined"?window:{});
