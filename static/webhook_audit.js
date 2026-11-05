"use strict";
/* Read-only presentation of *local* signed Sandbox webhook outcomes.
   No identifiers, names, webhooks, captures or remote provider calls. */
(function(root){
 const TYPES=[
  ["capture_recorded","Captured and verified locally"],
  ["capture_already_recorded","Duplicate capture already settled"],
  ["unmatched_order","Unknown local order"],
  ["missing_order_reference","Missing provider order reference"],
  ["amount_or_currency_mismatch","Amount/currency mismatch"],
  ["invalid_capture_payload","Invalid capture details"],
  ["ignored_event_type","Other signed event"],
  ["legacy_unclassified","Pre-audit historical event"]
 ];
 const NEEDS_REVIEW=new Set([
  "unmatched_order","missing_order_reference",
  "amount_or_currency_mismatch","invalid_capture_payload",
  "legacy_unclassified"
 ]);
 const validInt=n=>Number.isSafeInteger(n)&&n>=0;
 function presentation(data){
  if(!data||data.mode!=="PAYPAL_SANDBOX"||
     data.source!=="current_local_sqlite_signed_events_only"||
     !validInt(data.total_events)||!validInt(data.manual_review_events)||
     !data.outcomes||typeof data.outcomes!=="object"||Array.isArray(data.outcomes)||
     Object.keys(data.outcomes).length!==TYPES.length||
     !TYPES.every(([name])=>validInt(data.outcomes[name])))
   throw Error("Invalid signed webhook audit response");
  const all=TYPES.reduce((acc,[name])=>acc+data.outcomes[name],0);
  const manual=TYPES.reduce((acc,[name])=>
   acc+(NEEDS_REVIEW.has(name)?data.outcomes[name]:0),0);
  if(!Number.isSafeInteger(all)||!Number.isSafeInteger(manual)||
     data.total_events!==all||data.manual_review_events!==manual)
   throw Error("Inconsistent signed webhook audit counts");
  return {
   headline:manual?
    manual+" signed webhook event(s) need manual review":
    all?"No locally flagged signed webhook deliveries":
    "No signed webhooks recorded in this local database",
   needsReview:manual>0,
   rows:TYPES.map(([name,label])=>({
    label,count:data.outcomes[name],needsReview:NEEDS_REVIEW.has(name)
   })),
   notice:"Only signed events retained in current local SQLite are counted. "+
    "A missing database record does not mean PayPal has no order or capture. "+
    "No provider lookup, payment mutation or automatic retry occurs. "+
    "Review the original PayPal Sandbox transactions manually."
  };
 }
 if(typeof module!=="undefined"&&module.exports)module.exports={presentation};
 else root.CircleSplitWebhookAudit={presentation};
})(typeof window!=="undefined"?window:{});
