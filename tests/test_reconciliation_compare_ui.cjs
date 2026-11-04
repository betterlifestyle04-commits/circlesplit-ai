"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");
const {createHash,webcrypto}=require("node:crypto");
const compare=require("../static/reconciliation_compare.js");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const start=html.indexOf("async function compareLocalReconciliationFiles(){");
const end=html.indexOf("async function paypalCheckout(pid){",start);
assert.ok(start>0&&end>start,"Missing private comparison handler");
const script=html.slice(start,end);
const epoch="11111111-1111-4111-8111-111111111111";

function snapshot(records,date){
 return {
  app:"CircleSplit AI",kind:"paypal-sandbox-reconciliation-manifest",
  schema_version:1,mode:"PAYPAL_SANDBOX",currency:"USD",
  record_count:records.length,records,
  records_sha256:createHash("sha256").update(compare.canonical(records),"utf8").digest("hex"),
  importable:false,storage_epoch:epoch,generated_at:date
 };
}
function payment(status,capture){
 return {
  payment_id:1,event_id:2,person_id:3,event_name:"Demo",
  participant_name:"Tester",amount_cents:1000,status,
  created_at:"2026-11-04T18:00:00+00:00",
  paypal_order_id:"SANDBOX-ORDER-1",paypal_capture_id:capture
 };
}
function file(data){
 const dataText=typeof data==="string"?data:JSON.stringify(data);
 return {size:Buffer.byteLength(dataText),text:async()=>dataText};
}
function harness(old,newer){
 const all=new Map(),requests=[];
 function el(id){
  if(!all.has(id))all.set(id,{
   id,files:[],value:"private-selection",textContent:"",
   disabled:false,className:"",children:[],
   replaceChildren(){this.children=[]},
   appendChild(child){this.children.push(child)}
  });
  return all.get(id);
 }
 el("snapshot-compare-before").files=old?[file(old)]:[];
 el("snapshot-compare-after").files=newer?[file(newer)]:[];
 const context=vm.createContext({
  window:{crypto:webcrypto,CircleSplitReconciliationCompare:compare},
  document:{createElement:tag=>({
   tagName:tag,children:[],textContent:"",className:"",
   appendChild(child){this.children.push(child)}
  })},
  el,
  fetch(){requests.push("fetch");throw Error("Uploaded a private file")},
  request(){requests.push("request");throw Error("Uploaded a private file")}
 });
 vm.runInContext(script,context,{timeout:2000});
 return {run:vm.runInContext("compareLocalReconciliationFiles",context),
         el,requests};
}

test("comparison runs only on browser file contents, clears private selections",async()=>{
 const before=snapshot([payment("created",null)],"2026-11-04T20:00:00+00:00");
 const after=snapshot([payment("completed","CAPTURE-123")],"2026-11-04T21:00:00+00:00");
 const h=harness(before,after);
 await h.run();
 assert.deepEqual(h.requests,[]);
 assert.match(h.el("snapshot-compare-status").textContent,/Same database incarnation/);
 assert.match(h.el("snapshot-compare-status").textContent,/digests verified/);
 assert.equal(h.el("snapshot-compare-results").children.length,3);
 assert.match(h.el("snapshot-compare-results").children[1].textContent,/Newly completed locally: 1/);
 assert.equal(h.el("snapshot-compare-before").value,"");
 assert.equal(h.el("snapshot-compare-after").value,"");
 assert.equal(h.el("snapshot-compare-run").disabled,false);
});

test("invalid snapshot fails closed, doesn't transmit, and clears file inputs",async()=>{
 const before=snapshot([payment("completed","CAPTURE-123")],"2026-11-04T20:00:00+00:00");
 const after=snapshot([payment("completed","CAPTURE-123")],"2026-11-04T21:00:00+00:00");
 before.records[0].amount_cents++;
 const h=harness(before,after);
 await h.run();
 assert.deepEqual(h.requests,[]);
 assert.match(h.el("snapshot-compare-status").textContent,/digest does not match/);
 assert.equal(h.el("snapshot-compare-results").children.length,0);
 assert.equal(h.el("snapshot-compare-before").value,"");
 assert.equal(h.el("snapshot-compare-after").value,"");
 assert.equal(h.el("snapshot-compare-run").disabled,false);
});

test("comparison UI makes local-only and no-settlement limitations explicit",()=>{
 assert.match(html,/id="snapshot-compare-before"/);
 assert.match(html,/id="snapshot-compare-after"/);
 assert.match(html,/id="snapshot-compare-run"/);
 assert.match(html,/src="\/static\/reconciliation_compare.js"/);
 assert.match(html,/both files are read locally/i);
 assert.match(html,/never uploaded to CircleSplit or PayPal/i);
 assert.match(script,/beforeInput.value="";afterInput.value=""/);
 assert.doesNotMatch(script,/fetch\(/);
 assert.doesNotMatch(script,/\.post\(/);
});
