const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const begin=html.indexOf("async function runLedgerAudit(){");
const end=html.indexOf("let recoveryOffset=0,recoveryLimit=50;",begin);
assert.ok(begin>0&&end>begin,"Missing integrity audit UI");
const code=html.slice(begin,end);

function harness(data,{fail=false}={}){
 const elements=new Map();
 const calls=[];
 function el(id){
  if(!elements.has(id)){
   const node={id,textContent:"",disabled:false,children:[],className:"",
    appendChild(c){this.children.push(c)},
    replaceChildren(){this.children=[]},
   };
   elements.set(id,node);
  }
  return elements.get(id);
 }
 const context=vm.createContext({
  el,
  document:{createElement:tag=>({
   tag,textContent:"",className:"",children:[],
   appendChild(child){this.children.push(child)},
  })},
  request:async url=>{
   calls.push(url);
   if(fail)throw Error("Audit API unavailable");
   return data;
  },
  Number,Object,Error
 });
 vm.runInContext(code,context,{timeout:2000});
 return {run:vm.runInContext("runLedgerAudit",context),el,calls};
}

test("a consistent empty ledger is not misleadingly called settled",async()=>{
 const view=harness({mode:"PAYPAL_SANDBOX",status:"locally_consistent",
  issue_count:0,payment_records_checked:0,unresolved_orders:0,
  issue_counts:{},findings:[],findings_truncated:false});
 await view.run();
 assert.deepEqual(view.calls,["/api/paypal/ledger-audit"]);
 assert.match(view.el("ledger-audit-status").textContent,/No local inconsistencies/);
 assert.match(view.el("ledger-audit-findings").children[0].textContent,/cannot verify PayPal settlement/);
 assert.equal(view.el("ledger-audit-run").disabled,false);
});

test("audit safely renders codes, counts and affected local IDs",async()=>{
 const view=harness({mode:"PAYPAL_SANDBOX",status:"needs_review",
  issue_count:2,payment_records_checked:10,unresolved_orders:4,
  issue_counts:{payment_amount_mismatch:1,completed_without_capture:1},
  findings:[
   {code:"payment_amount_mismatch",payment_id:8,event_id:2,person_id:5},
   {code:"completed_without_capture",payment_id:9,event_id:2,person_id:5}
  ],findings_truncated:false});
 await view.run();
 assert.match(view.el("ledger-audit-status").textContent,/2 integrity findings/);
 assert.match(view.el("ledger-audit-findings").children[0].textContent,/payment amount mismatch: 1/);
 const items=view.el("ledger-audit-findings").children[1].children;
 assert.equal(items.length,2);
 assert.match(items[0].textContent,/payment #8, event #2, person #5/);
 assert.equal(view.el("ledger-audit-run").disabled,false);
});

test("audit exposes additional findings message and safely recovers from failures",async()=>{
 const d={mode:"PAYPAL_SANDBOX",status:"needs_review",
  issue_count:140,payment_records_checked:150,unresolved_orders:120,
  issue_counts:{bad_record:140},
  findings:[{code:"bad_record",payment_id:1,event_id:null,person_id:null}],
  findings_truncated:true};
 const view=harness(d);
 await view.run();
 assert.match(view.el("ledger-audit-findings").children[2].textContent,/Additional integrity findings/);
 const error=harness(d,{fail:true});
 await error.run();
 assert.match(error.el("ledger-audit-status").textContent,/Audit API unavailable/);
 assert.equal(error.el("ledger-audit-run").disabled,false);
});

test("audit is read-only and visible only in the private workspace",()=>{
 assert.match(html,/id="ledger-audit-run"/);
 assert.match(html,/Local payment integrity audit/);
 assert.match(code,/\/api\/paypal\/ledger-audit/);
 assert.doesNotMatch(code,/\/api\/paypal\/capture/);
 assert.doesNotMatch(code,/\bpost\(/);
});
