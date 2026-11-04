const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const html=fs.readFileSync(path.join(__dirname,"../static/index.html"),"utf8");
const start=html.indexOf("async function downloadReconciliationManifest(){");
const end=html.indexOf("async function paypalCheckout(pid){",start);
assert.ok(start>0&&end>start,"Expected private reconciliation download function");
const script=html.slice(start,end);

function harness(result,{confirmed=true,error=null}={}){
 const calls=[],downloads=[],messages=[];
 const button={disabled:false};
 const context=vm.createContext({
  window:{confirm(){calls.push("confirm");return confirmed}},
  el:()=>button,
  request:async url=>{calls.push(url);if(error)throw Error(error);return result},
  offerDownload:(...args)=>downloads.push(args),
  notice:(...args)=>messages.push(args),
  Date,JSON,Array,RegExp,Error
 });
 vm.runInContext(script,context,{timeout:2000});
 return {execute:vm.runInContext("downloadReconciliationManifest",context),
         calls,downloads,messages,button};
}

const valid={
 kind:"paypal-sandbox-reconciliation-manifest",schema_version:1,
 mode:"PAYPAL_SANDBOX",importable:false,record_count:1,
 storage_epoch:"01234567-89ab-cdef-0123-456789abcdef",
 records:[{payment_id:1,status:"capturing",paypal_order_id:"SANDBOX-ORDER"}]
};

test("the download requires a privacy confirmation",async()=>{
 const h=harness(valid,{confirmed:false});
 await h.execute();
 assert.deepEqual(h.calls,["confirm"]);
 assert.equal(h.downloads.length,0);
 assert.equal(h.button.disabled,false);
});

test("the download saves a private JSON file with the full reconciliation payload",async()=>{
 const h=harness(valid);
 await h.execute();
 assert.deepEqual(h.calls,["confirm","/api/paypal/reconciliation-export"]);
 assert.equal(h.downloads.length,1);
 const [filename,json,mime]=h.downloads[0];
 assert.match(filename,/^circlesplit-private-sandbox-reconciliation-\d{4}-\d{2}-\d{2}-01234567-89a\.json$/);
 assert.equal(mime,"application/json;charset=utf-8");
 assert.deepEqual(JSON.parse(json),valid);
 assert.match(h.messages[0][0],/not a receipt or backup/);
 assert.equal(h.button.disabled,false);
});

test("invalid server manifest cannot be silently downloaded",async()=>{
 for(const invalid of [
  {...valid,kind:"planning-backup"},
  {...valid,mode:"LIVE"},
  {...valid,importable:true},
  {...valid,record_count:2},
  {...valid,records:null},
 ]){
  const h=harness(invalid);
  await h.execute();
  assert.equal(h.downloads.length,0);
  assert.equal(h.button.disabled,false);
  assert.match(h.messages[0][0],/Unexpected reconciliation manifest/);
 }
});

test("network failure always re-enables download",async()=>{
 const h=harness(valid,{error:"Read-only API unavailable"});
 await h.execute();
 assert.equal(h.downloads.length,0);
 assert.equal(h.button.disabled,false);
 assert.match(h.messages[0][0],/could not be downloaded/);
});

test("the UI discloses private identifiers and never offers an import for the manifest",()=>{
 assert.match(html,/id="recovery-export"/);
 assert.match(html,/not a PayPal receipt, verified settlement, or restorable database backup/);
 assert.match(script,/NOT proof of payment or an importable backup/);
 assert.doesNotMatch(script,/fetch\([^)]*\{\s*method\s*:\s*["']POST/);
});
