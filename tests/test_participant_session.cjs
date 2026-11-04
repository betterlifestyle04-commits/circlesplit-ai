const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const vm=require("node:vm");

const html=fs.readFileSync(path.join(__dirname,"../static/participant.html"),"utf8");
const scripts=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length,1,"Expected exactly one participant inline script");
const code=scripts[0][1];
const TOKEN_A="A".repeat(43);
const TOKEN_B="B".repeat(43);

function boot({fragment="",saved=undefined,storageUnavailable=false}={}){
 const elements=new Map(),pending=[],replaced=[],storage=new Map();
 const handlers=new Map();
 if(saved!==undefined)storage.set("circlesplit-participant-token",saved);
 function el(id){
  if(!elements.has(id)){
   elements.set(id,{
    textContent:"",hidden:false,disabled:false,value:"",className:"",style:{},
    classList:{add(){}},children:[],
    addEventListener(event,fn){handlers.set(id+":"+event,fn)},
    replaceChildren(){this.children=[]},
    appendChild(n){this.children.push(n)},
    setAttribute(){},
   });
  }
  return elements.get(id);
 }
 const sessionStorage={
  getItem(key){if(storageUnavailable)throw Error("Storage unavailable");return storage.get(key)||null},
  setItem(key,value){if(storageUnavailable)throw Error("Storage unavailable");storage.set(key,value)},
  removeItem(key){if(storageUnavailable)throw Error("Storage unavailable");storage.delete(key)}
 };
 const context=vm.createContext({
  document:{
   getElementById:el,
   createElement:tag=>({tag,textContent:"",className:"",children:[],
    setAttribute(){},appendChild(node){this.children.push(node)}}),
   body:{appendChild(){}},
  },
  window:{location:{hash:fragment,pathname:"/participant",search:""},
    confirm:()=>true},
  sessionStorage,
  history:{replaceState(...args){replaced.push(args)}},
  URLSearchParams,
  fetch:(url,init)=>new Promise(resolve=>pending.push({url,init,resolve})),
  setTimeout(){},URL,Blob,console,
 });
 vm.runInContext(code,context,{timeout:2000});
 return {context,elements,el,handlers,storage,pending,replaced};
}

function fakeOverview(){
 return {event_name:"A private event",event_date:"2026-11-16",participant:"Private tester",
  share_cents:1100,expires_at:"2099-01-01T00:00:00Z",agenda:[],
  agenda_revision:0,rsvp_status:"pending",approved:false,status:"unpaid",
  checkout_started:false,approval_withdrawn:false};
}
async function complete(pending,payload=fakeOverview()){
 assert.ok(pending,"Expected one pending overview request");
 pending.resolve({ok:true,json:async()=>payload});
 // Let both nested fetch/json promises and the view-render continuation run.
 await new Promise(resolve=>setImmediate(resolve));
}
function select(context,fragment,saved){
 return vm.runInContext("selectInvitationToken",context)(fragment,saved);
}

test("new valid link overrides an older saved invitation and cleans address bar",async()=>{
 const view=boot({fragment:"#token="+TOKEN_B,saved:TOKEN_A});
 assert.equal(view.storage.get("circlesplit-participant-token"),TOKEN_B);
 assert.equal(view.pending.length,1);
 assert.equal(view.pending[0].init.headers.Authorization,"Bearer "+TOKEN_B);
 assert.equal(view.replaced.length,1);
 assert.equal(view.replaced[0][2],"/participant");
 await complete(view.pending[0]);
 assert.equal(view.el("person").textContent,"Private tester");
 assert.equal(view.el("details").hidden,false);
});

test("malformed new invitation never falls back to previous participant",()=>{
 for(const hash of [
  "#token=invalid", "#token="+TOKEN_A+"&token="+TOKEN_B,
  "#source=external", "#token="+TOKEN_A+"&extra=yes",
  "#token="+TOKEN_A+"%20", "#token=%00"+TOKEN_A,
 ]){
  const view=boot({fragment:hash,saved:TOKEN_A});
  assert.equal(view.storage.has("circlesplit-participant-token"),false,hash);
  assert.equal(view.pending.length,0,hash);
  assert.equal(view.el("details").hidden,true,hash);
  assert.equal(view.replaced.length,1,hash);
 }
});

test("a refresh can reuse an existing invitation in its own tab",async()=>{
 const view=boot({saved:TOKEN_A});
 assert.equal(view.pending.length,1);
 assert.equal(view.pending[0].init.headers.Authorization,"Bearer "+TOKEN_A);
 assert.equal(view.replaced.length,0);
 await complete(view.pending[0]);
 assert.equal(view.el("title").textContent,"A private event");
});

test("a valid link works even if browser sessionStorage is blocked",()=>{
 const view=boot({fragment:"#token="+TOKEN_A,storageUnavailable:true});
 assert.equal(view.pending.length,1);
 assert.equal(view.pending[0].init.headers.Authorization,"Bearer "+TOKEN_A);
 assert.equal(view.replaced.length,1);
});

test("forgetting an invitation prevents a late response restoring private data",async()=>{
 const view=boot({fragment:"#token="+TOKEN_A});
 assert.equal(view.pending.length,1);
 view.handlers.get("forget-invitation:click")();
 assert.equal(view.el("details").hidden,true);
 assert.equal(view.el("title").textContent,"Invitation cleared");
 assert.equal(view.storage.has("circlesplit-participant-token"),false);
 await complete(view.pending[0]);
 assert.equal(view.el("details").hidden,true);
 assert.equal(view.el("title").textContent,"Invitation cleared");
 assert.equal(view.el("description").textContent.includes("fresh private link"),true);
});

test("selector fails closed on invalid storage and unexpected link parameters",()=>{
 const view=boot({});
 const evaluate=fragment=>select(view.context,fragment,TOKEN_A);
 assert.equal(evaluate("#token="+TOKEN_B).source,"new_link");
 assert.equal(evaluate("#token="+TOKEN_B).token,TOKEN_B);
 assert.equal(evaluate("#token=short").source,"invalid_link");
 assert.equal(evaluate("#token="+TOKEN_A+"&x=1").token,"");
 assert.equal(evaluate("#token="+TOKEN_A+"&token="+TOKEN_B).token,"");
 assert.equal(select(view.context,"",TOKEN_A).source,"saved");
 assert.equal(select(view.context,"","bad").source,"missing");
});

test("participant controls disclose that forgetting is local-only",()=>{
 assert.match(html,/id="forget-invitation"/);
 assert.match(html,/does not revoke the link or undo a submitted RSVP or approval/);
 assert.match(code,/invitationVersion\+\+/);
 assert.match(code,/expectedVersion!==invitationVersion/);
});

test("withdrawal button calls private API and reflects renewed-approval option",async()=>{
 const view=boot({fragment:"#token="+TOKEN_A});
 await complete(view.pending[0],{...fakeOverview(),approved:true});
 assert.equal(view.el("withdraw-approval").disabled,false);
 const click=view.handlers.get("withdraw-approval:click")();
 assert.equal(view.pending.length,2);
 assert.equal(view.pending[1].url,"/api/participant/withdraw");
 assert.equal(view.pending[1].init.method,"POST");
 assert.equal(view.pending[1].init.headers.Authorization,"Bearer "+TOKEN_A);
 view.pending[1].resolve({ok:true,json:async()=>({
  ok:true,already_withdrawn:false,approval_withdrawn:true,payment_changed:false
 })});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(view.pending.length,3,"Withdrawal should refresh the participant state");
 await complete(view.pending[2],{...fakeOverview(),approval_withdrawn:true});
 await click;
 assert.equal(view.el("approval").textContent,"Withdrawn by private link");
 assert.equal(view.el("withdraw-approval").disabled,true);
 assert.equal(view.el("approve").disabled,false,
  "Re-approving through private link should remain available");
 assert.match(view.el("message").textContent,/Approval withdrawn/);
});

test("started checkout disables both approval and withdrawal actions",async()=>{
 const view=boot({fragment:"#token="+TOKEN_A});
 await complete(view.pending[0],{...fakeOverview(),checkout_started:true,approved:true});
 assert.equal(view.el("payment").textContent,"Sandbox checkout started");
 assert.equal(view.el("approve").disabled,true);
 assert.equal(view.el("withdraw-approval").disabled,true);
});

test("withdrawal controls explicitly distinguish consent from refund",()=>{
 assert.match(html,/id="withdraw-approval"/);
 assert.match(html,/does not cancel a checkout already started/);
 assert.match(code,/\/api\/participant\/withdraw/);
});
