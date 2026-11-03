"use strict";
/* No export is an invoice, payment demand, or independently verified statement. */
const CLOSEOUT_LABELS={
 needs_review:"Review inconsistencies",
 needs_setup:"Set up event",
 orders_pending:"Sandbox orders pending",
 sandbox_captures_cover_budget:"Sandbox captures cover planned budget",
 demo_activity:"Simulations recorded — not verified funding",
 unverified:"Sandbox funding unverified"
};
function closeoutLabel(stage){
 return CLOSEOUT_LABELS[stage]||"Status unavailable";
}
function closeoutMoney(cents){
 if(!Number.isSafeInteger(Number(cents)))throw Error("Invalid closeout amount");
 return (Number(cents)/100).toFixed(2);
}
function closeoutCsvRows(report){
 if(!report||!Array.isArray(report.participants)||!report.summary)
  throw Error("Closeout preview is unavailable");
 const rows=[["CircleSplit AI — FICTIONAL SANDBOX CLOSEOUT PREVIEW"],
  ["Not an invoice, debt, payout confirmation or real-money transaction"],
  ["Event","Date","Stage","Planned USD","Verified PayPal sandbox USD","Simulated USD","Unverified against sandbox USD","Pending PayPal sandbox orders"],
  [report.event_name,report.event_date,closeoutLabel(report.stage),
   closeoutMoney(report.summary.planned_cents),
   closeoutMoney(report.summary.verified_sandbox_cents),
   closeoutMoney(report.summary.simulated_cents),
   closeoutMoney(report.summary.unverified_against_sandbox_cents),
   report.summary.pending_orders],
  [],
  ["Participant","Assigned share USD","RSVP","Approval recorded","Approval source","Local status","Verified sandbox captures USD","Simulation USD","Unverified against sandbox USD","Pending orders"]];
 for(const p of report.participants){
  rows.push([p.name,closeoutMoney(p.share_cents),p.rsvp_status,
    p.approved?"Yes":"No",p.approval_source,p.recorded_status,
    closeoutMoney(p.verified_sandbox_cents),closeoutMoney(p.simulated_cents),
    closeoutMoney(p.unverified_against_sandbox_cents),p.pending_orders]);
 }
 rows.push([],["Report is read-only and based on temporary local records. It does not check PayPal in real time."]);
 return rows;
}
function closeoutBrief(report){
 if(!report||!report.summary)throw Error("Closeout preview is unavailable");
 const d=report.summary;
 return [
  "CircleSplit AI — SANDBOX CLOSEOUT PREVIEW",
  "Event: "+String(report.event_name||""),
  "Date: "+String(report.event_date||""),
  "Status: "+closeoutLabel(report.stage),
  "Planned group budget: "+closeoutMoney(d.planned_cents)+" USD",
  "Verified PayPal SANDBOX captures (local ledger): "+closeoutMoney(d.verified_sandbox_cents)+" USD",
  "Simulated contributions (not PayPal): "+closeoutMoney(d.simulated_cents)+" USD",
  "Unverified against PayPal sandbox: "+closeoutMoney(d.unverified_against_sandbox_cents)+" USD",
  "Pending PayPal sandbox orders: "+d.pending_orders,
  "Pending share approvals: "+d.approvals_pending,
  "RSVP declines: "+d.rsvp_declined,
  "Preparation completed: "+d.tasks_completed+"/"+d.tasks_total,
  "",
  "READ-ONLY: No event was finalized, closed or archived.",
  "Sandbox transactions are not real money. Unverified amounts are NOT invoices, debts or payment requests.",
  "This report uses temporary local records and does not independently contact PayPal."
 ].join("\n");
}
if(typeof module!=="undefined"&&module.exports)
 module.exports={closeoutLabel,closeoutMoney,closeoutCsvRows,closeoutBrief};
