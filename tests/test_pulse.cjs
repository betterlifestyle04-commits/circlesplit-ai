const {test}=require("node:test");
const assert=require("node:assert/strict");
const {pulseDate,pulseEvent,pulseSummary,pulseBriefing}=require("../static/pulse.js");
const d="2026-11-03",event={id:1,name:"Volleyball",date:"2026-11-06",total_cents:22000,
 sandbox_cents:1100,simulated_cents:1100,
 people:[{share_cents:11000,approved:1,status:"sandbox_paid"},{share_cents:11000,approved:0,status:"unpaid"}],
 tasks:[{completed:1},{completed:0}]};
test("date classification is deterministic",()=>{
 assert.equal(pulseDate("2026-11-06",d),"soon");assert.equal(pulseDate("2026-11-02",d),"past");
 assert.equal(pulseDate("2026-02-31",d),"unknown");});
test("simulation cannot inflate verified sandbox total",()=>{
 const p=pulseEvent(event,[],d);assert.equal(p.verified,1100);assert.equal(p.outstanding,20900);
 assert.equal(p.approval,1);assert.equal(p.status,"Needs approval");
 assert.ok(p.actions.some(a=>a.code==="tasks"));});
test("unverified PayPal order is highest-priority",()=>{
 const p=pulseSummary([event],[{event_id:1,status:"created"}],d);
 assert.equal(p.orders,1);assert.equal(p.actions[0].code,"orders");assert.equal(p.actions[0].tab,"activity");});
test("inconsistent allocations and empty budgets are blockers",()=>{
 const p=pulseEvent({...event,total_cents:23000},[],d);
 assert.equal(p.status,"Needs setup");assert.ok(p.actions.some(a=>a.code==="allocation"));
 const empty=pulseEvent({id:2,name:"Empty",date:"2026-11-05",people:[],tasks:[]},[],d);
 assert.ok(empty.actions.some(a=>a.code==="budget"));assert.ok(empty.actions.some(a=>a.code==="people"));});
test("progress is never falsely described as payment success",()=>{
 const p=pulseEvent({...event,sandbox_cents:0,people:event.people.map(p=>({...p,approved:1,status:"unpaid"})),tasks:[{completed:1}]},[],d);
 assert.equal(p.status,"Planning progressing");assert.equal(p.verified,0);});
test("event briefing labels sandbox amounts and rejects invoice claims",()=>{
 const b=pulseBriefing(event);
 assert.match(b,/NOT an invoice/);assert.match(b,/Simulated contributions excluded/);assert.match(b,/209\.00 USD/);});
test("declined RSVP becomes organizer review rather than payment reminder",()=>{
 const declined={...event,people:[...event.people.map((x,i)=>i===1?{...x,rsvp_status:"declined"}:x)]};
 const p=pulseEvent(declined,[],d);
 assert.equal(p.declined,1);
 assert.equal(p.approval,0);
 assert.ok(p.actions.some(x=>x.code==="attendance"&&x.tab==="events"));
 assert.ok(!p.actions.some(x=>x.code==="approval"));
 assert.equal(p.outstanding,20900); // RSVP never reallocates existing shares.
});
