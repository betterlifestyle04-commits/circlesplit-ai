"use strict";
/* Read-only presentation of aggregate, local-only Sandbox triage figures.
   Never renders payment IDs, private people, source strings, or PayPal links. */
(function(root){
 const CATEGORIES=[
  "inconsistent_local_record","unknown_order_creation",
  "uncertain_capture_attempt","awaiting_provider_confirmation",
  "locally_completed"
 ];
 const integer=x=>Number.isSafeInteger(x)&&x>=0;
 const sum=(a,b)=>a+b;
 function presentation(input){
  if(!input||input.mode!=="PAYPAL_SANDBOX"||
     input.source!=="current_local_sqlite_only"||
     !["needs_manual_review","pending_provider_confirmation","no_local_unresolved_records"].includes(input.status)||
     !input.categories||typeof input.categories!=="object"||
     !CATEGORIES.every(k=>integer(input.categories[k]))||
     Object.keys(input.categories).length!==CATEGORIES.length||
     ![input.total_records,input.attention_count,input.priority_review_count,
       input.older_than_60_minutes,input.unparseable_created_timestamps,
       input.unverified_request_face_value_cents].every(integer)){
   throw Error("Invalid local recovery risk summary");
  }
  const c=input.categories;
  const total=CATEGORIES.reduce((n,k)=>n+c[k],0);
  const critical=c.inconsistent_local_record+c.unknown_order_creation+c.uncertain_capture_attempt;
  const attention=critical+c.awaiting_provider_confirmation;
  const expected=critical?"needs_manual_review":
   attention?"pending_provider_confirmation":"no_local_unresolved_records";
  if(!Number.isSafeInteger(total)||total!==input.total_records||
     critical!==input.priority_review_count||attention!==input.attention_count||
     input.status!==expected||input.older_than_60_minutes>attention||
     input.unparseable_created_timestamps>total){
   throw Error("Inconsistent local recovery risk summary");
  }
  const usd=n=>"$"+(n/100).toLocaleString("en-US",{
   minimumFractionDigits:2,maximumFractionDigits:2
  });
  return {
   heading:critical?"Manual investigation needed":
      attention?"Pending Sandbox verification":"No unresolved local orders",
   severity:critical?"orange":"neutral",
   facts:[
    ["Unknown order creation",c.unknown_order_creation],
    ["Capture attempt uncertain",c.uncertain_capture_attempt],
    ["Local ledger anomalies",c.inconsistent_local_record],
    ["Awaiting provider confirmation",c.awaiting_provider_confirmation],
    ["Older than 60 min (unresolved)",input.older_than_60_minutes],
    ["Locally completed with capture ID",c.locally_completed]
   ],
   faceValue:usd(input.unverified_request_face_value_cents),
   unknownAge:input.unparseable_created_timestamps,
   disclosure:"Unverified request face value is NOT money collected, lost, or owed. "+
    "This reflects only current local Sandbox records. After a database reset, "+
    "old provider orders may be absent. Review in PayPal Sandbox; never retry "+
    "uncertain creation or capture requests automatically."
  };
 }
 if(typeof module!=="undefined"&&module.exports)module.exports={presentation};
 else root.CircleSplitRecoveryTriage={presentation};
})(typeof window!=="undefined"?window:{});
