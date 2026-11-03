const {test}=require("node:test");
const assert=require("node:assert/strict");
const {directoryView,explainShare,validDay}=require("../static/directory.js");
test("directory search and chronological sorting",()=>{
 const base={people:[{rsvp_status:"going",status:"unpaid",approved:true,share_cents:100}],tasks:[],total_cents:100};
 const events=[{...base,id:3,name:"Past volleyball",date:"2026-10-01",note:"court"},
  {...base,id:2,name:"Future padel",date:"2026-12-01",note:"rackets"},
  {...base,id:1,name:"Friday volleyball",date:"2026-11-06",note:"court"}];
 assert.deepEqual(directoryView(events,"volleyball","all","soonest","2026-11-03").map(e=>e.id),[1,3]);
 assert.deepEqual(directoryView(events,"","upcoming","soonest","2026-11-03").map(e=>e.id),[1,2]);
 assert.deepEqual(directoryView(events,"","past","soonest","2026-11-03").map(e=>e.id),[3]);
 assert.equal(directoryView(events,"rackets")[0].id,2);
 assert.equal(validDay("2026-02-30"),false);
});
test("directory prioritizes attention and highest budgets",()=>{
 const e={date:"2026-11-10",tasks:[],people:[],name:"Event"};
 const events=[{...e,id:1,total_cents:0},{...e,id:2,total_cents:5000}];
 assert.deepEqual(directoryView(events,"","all","budget","2026-11-03").map(e=>e.id),[2,1]);
 assert.equal(directoryView(events,"","needs-attention").length,2);
});
test("exact-cent explanation uses stable largest remainders",()=>{
 const event={id:1,name:"Test",strategy:"equal",total_cents:100,people:[
  {id:5,name:"B",weight:10,share_cents:33},
  {id:2,name:"A",weight:1,share_cents:34},
  {id:9,name:"C",weight:1,share_cents:33}]};
 const p=explainShare(event,2);
 assert.equal(p.expectedCents,34);assert.equal(p.baseCents,33);assert.equal(p.roundingCents,1);
 assert.equal(p.totalWeight,3);assert.equal(p.effectiveWeight,1);assert.equal(p.consistent,true);
 assert.equal(explainShare(event,9).roundingCents,0);
});
test("weighted split explanation is consistent with integer-cents allocation",()=>{
 const event={strategy:"weighted",total_cents:100,people:[
  {id:6,name:"Heavy",weight:3,share_cents:50},
  {id:1,name:"Light",weight:1,share_cents:17},
  {id:3,name:"Medium",weight:2,share_cents:33}]};
 const p=explainShare(event,1);
 assert.equal(p.totalWeight,6);assert.equal(p.baseCents,16);
 assert.equal(p.roundingCents,1);assert.equal(p.expectedCents,17);
 assert.equal(explainShare(event,3).expectedCents,33);
 assert.equal(explainShare(event,6).expectedCents,50);
});
test("tampered allocation is flagged rather than explained as correct",()=>{
 const e={strategy:"equal",total_cents:100,people:[
   {id:1,name:"P1",share_cents:30},{id:2,name:"P2",share_cents:70}]};
 const x=explainShare(e,1);
 assert.equal(x.expectedCents,50);assert.equal(x.recordedCents,30);assert.equal(x.consistent,false);
});
test("missing or invalid participants are rejected",()=>{
 assert.throws(()=>explainShare({people:[],total_cents:50},1));
 assert.throws(()=>explainShare({people:[{id:1,weight:12}],total_cents:100,strategy:"weighted"},1));
 assert.throws(()=>explainShare({people:[{id:2,weight:1,share_cents:100}],total_cents:100},5));
});
