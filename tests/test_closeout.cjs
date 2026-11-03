const {test}=require("node:test");
const assert=require("node:assert/strict");
const {closeoutLabel,closeoutCsvRows,closeoutBrief}=require("../static/closeout.js");
const example={event_id:1,event_name:"Volleyball",event_date:"2026-11-06",stage:"demo_activity",
 summary:{planned_cents:22000,verified_sandbox_cents:1100,simulated_cents:1100,
 unverified_against_sandbox_cents:20900,pending_orders:1,approvals_pending:2,
 rsvp_declined:1,tasks_completed:2,tasks_total:5},
 participants:[{name:"Alex",share_cents:1100,rsvp_status:"going",approved:true,
 approval_source:"participant_link",recorded_status:"sandbox_paid",
 verified_sandbox_cents:1100,simulated_cents:0,unverified_against_sandbox_cents:0,pending_orders:0}]};
test("stage labels do not suggest actual final settlement",()=>{
 assert.match(closeoutLabel("sandbox_captures_cover_budget"),/Sandbox/);
 assert.match(closeoutLabel("demo_activity"),/not verified/);
 assert.equal(closeoutLabel("unknown"),"Status unavailable");
});
test("group briefing excludes individual participant names and secrets",()=>{
 const text=closeoutBrief(example);
 assert.match(text,/SANDBOX CLOSEOUT PREVIEW/);
 assert.match(text,/Unverified against PayPal sandbox: 209\.00 USD/);
 assert.match(text,/Simulated contributions.*11\.00 USD/);
 assert.match(text,/NOT invoices, debts or payment requests/);
 assert.match(text,/does not independently contact PayPal/);
 assert.ok(!text.includes("Alex"));
});
test("CSV has correctly separated local simulation vs verified capture",()=>{
 const rows=closeoutCsvRows(example);
 assert.equal(rows[3][4],"11.00");
 assert.equal(rows[3][5],"11.00");
 assert.equal(rows[3][6],"209.00");
 assert.equal(rows[6][0],"Alex");
 assert.equal(rows[6][6],"11.00");
 assert.equal(rows[6][7],"0.00");
 assert.match(rows[1][0],/Not an invoice/);
 assert.ok(!JSON.stringify(rows).includes("capture_id"));
});
test("missing report fails closed and no imaginary money",()=>{
 assert.throws(()=>closeoutBrief({}),/unavailable/);
 assert.throws(()=>closeoutCsvRows(null),/unavailable/);
 assert.throws(()=>closeoutBrief({...example,summary:{...example.summary,planned_cents:NaN}}),/Invalid/);
});
