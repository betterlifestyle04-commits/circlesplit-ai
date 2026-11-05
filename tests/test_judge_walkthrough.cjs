"use strict";
const {test}=require("node:test");
const assert=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const {STEPS,SAMPLE_PROMPT,progress,verifiedPublicHealth,checkPublicSource,setupJudgeUI}
 =require("../static/judge_walkthrough.js");

const html=fs.readFileSync(path.join(__dirname,"../static/judge.html"),"utf8");
const GIT_SHA="84c3de492a6b31a00d5396031517db31c1f62fbd";

function harness({health={status:"ok",mode:"sandbox-only",git_commit:GIT_SHA},
                 clipboardEnabled=true}={}){
 const elements=new Map(),calls=[],copied=[];
 function element(id){
  if(!elements.has(id)){
   const obj={id,style:{width:""},textContent:"",disabled:false,
    className:"",classes:new Set(),handlers:{},attrs:new Map(),
    addEventListener(name,callback){this.handlers[name]=callback},
    getAttribute(name){return this.attrs.get(name)??null},
    setAttribute(name,value){this.attrs.set(name,String(value))},
    classList:null,
    async click(){return this.handlers.click()},
   };
   obj.classList={toggle(name,yes){if(yes)obj.classes.add(name);else obj.classes.delete(name)}};
   elements.set(id,obj);
  }
  return elements.get(id);
 }
 const buttons=STEPS.map(step=>{
  const button=element("step-"+step.id);
  button.setAttribute("data-judge-step",step.id);
  return button;
 });
 const doc={getElementById:element,querySelectorAll(selector){
  assert.equal(selector,"[data-judge-step]");
  return buttons;
 }};
 const fetchFn=async(url,opts)=>{
  calls.push({url,opts});
  return {ok:health!==null,json:async()=>health};
 };
 const clip=clipboardEnabled?{async writeText(value){copied.push(value)}}:null;
 const ui=setupJudgeUI(doc,fetchFn,clip);
 return {element,buttons,calls,copied,ui};
}

test("walkthrough defines exactly five accessible, separate evaluation scopes",()=>{
 assert.deepEqual(STEPS.map(s=>s.id),["public","ai","consent","paypal","evidence"]);
 assert.equal(STEPS.length,5);
 assert.equal(new Set(STEPS.map(s=>s.href)).size,STEPS.length);
 for(const s of STEPS) assert.match(html,new RegExp('id="'+s.href.slice(1)+'"'));
 assert.equal((html.match(/data-judge-step="/g)||[]).length,5);
 assert.match(html,/aria-label="Evaluation checklist steps"/);
 assert.match(html,/id="judge-progress-text" role="status"/);
 assert.match(html,/id="judge-source-status" role="status"/);
 assert.match(html,/PayPal sandbox PERSONAL buyer/);
 assert.match(html,/not the other participants' names or shares/i);
 assert.match(html,/No real funds/);
 assert.match(html,/Resilience lab/);
 assert.match(html,/2 hypothetical no-shows require 1 fictional replacement attendee/);
});

test("progress is local, ignores invalid keys, and needs explicit review",async()=>{
 const h=harness();
 assert.deepEqual(h.ui.progress(),{completed:0,total:5,percent:0});
 assert.equal(h.ui.currentStep(),"public");
 assert.match(h.element("judge-progress-text").textContent,/0 of 5/);
 await h.element("judge-review-toggle").click();
 assert.equal(h.ui.progress().completed,1);
 assert.equal(h.element("judge-progress-bar").style.width,"20%");
 assert(h.buttons[0].classes.has("done"));
 assert.match(h.element("judge-status").textContent,/not a test result/);
 await h.element("judge-next").click();
 assert.equal(h.ui.currentStep(),"ai");
 assert.equal(h.element("judge-step-detail").getAttribute("href"),"#judge-ai");
 assert.match(h.element("judge-current-expected").textContent,/\$235/);
 await h.element("judge-review-toggle").click();
 assert.equal(h.ui.progress().percent,40);
 await h.element("judge-prev").click();
 assert.equal(h.ui.currentStep(),"public");
 await h.element("judge-review-toggle").click();
 assert.equal(h.ui.progress().completed,1);
 assert.equal(h.calls.length,0,"Checklist must not transmit progress");
 assert.equal(progress(new Set(["bogus","paypal"])).completed,1);
});

test("navigation switches steps and disables nonexistent previous/next",async()=>{
 const h=harness();
 assert.equal(h.element("judge-prev").disabled,true);
 assert.equal(h.element("judge-next").disabled,false);
 await h.buttons[4].click();
 assert.equal(h.ui.currentStep(),"evidence");
 assert.equal(h.element("judge-next").disabled,true);
 assert.equal(h.element("judge-prev").disabled,false);
 assert.equal(h.buttons[4].getAttribute("aria-current"),"step");
 assert.equal(h.buttons[0].getAttribute("aria-current"),"false");
 assert.equal(h.element("judge-step-detail").getAttribute("href"),"#judge-evidence");
 assert.equal(h.calls.length,0);
});

test("copy sample note only reports success after browser clipboard accepts it",async()=>{
 const h=harness();
 await h.element("judge-copy-prompt").click();
 assert.deepEqual(h.copied,[SAMPLE_PROMPT]);
 assert.match(h.element("judge-status").textContent,/copied/);
 assert.equal(h.calls.length,0);
 const noClipboard=harness({clipboardEnabled:false});
 await noClipboard.element("judge-copy-prompt").click();
 assert.match(noClipboard.element("judge-status").textContent,/Could not copy/);
});

test("only explicit GET /health with omitted credentials checks source revision",async()=>{
 const h=harness();
 await h.element("judge-source-check").click();
 assert.equal(h.calls.length,1);
 assert.equal(h.calls[0].url,"/health");
 assert.equal(h.calls[0].opts.method,"GET");
 assert.equal(h.calls[0].opts.credentials,"omit");
 assert.equal(h.calls[0].opts.cache,"no-store");
 assert.match(h.element("judge-source-status").textContent,/revision 84c3de492a6b/);
 assert.match(h.element("judge-source-status").textContent,/does NOT test Gemini, PayPal/);
 assert.equal(h.element("judge-source-check").disabled,false);
 assert(!JSON.stringify(h.calls).includes("/api/paypal/"));
});

test("source check rejects invalid health and handles missing SHA and errors",async()=>{
 for(const input of [
  null,{status:"ok",mode:"LIVE",git_commit:GIT_SHA},
  {status:"error",mode:"sandbox-only",git_commit:GIT_SHA},
  {status:"ok",mode:"sandbox-only",git_commit:"../../abc"}
 ])assert.throws(()=>verifiedPublicHealth(input));
 assert.equal(verifiedPublicHealth({status:"ok",mode:"sandbox-only",git_commit:null}),null);
 const h=harness({health:{status:"ok",mode:"sandbox-only",git_commit:null}});
 await h.element("judge-source-check").click();
 assert.match(h.element("judge-source-status").textContent,/no deploy revision/);
 const down=harness({health:null});
 await down.element("judge-source-check").click();
 assert.match(down.element("judge-source-status").textContent,/unavailable/);
 assert.equal(down.element("judge-source-check").disabled,false);
 await assert.rejects(checkPublicSource(async()=>({ok:false})),/unavailable/);
});

test("guide provides accurate fictional expectations and sandbox-only guardrails",()=>{
 assert.match(SAMPLE_PROMPT,/\$180/);
 assert.match(SAMPLE_PROMPT,/\$25/);
 assert.match(SAMPLE_PROMPT,/\$30/);
 assert.match(STEPS[0].expected,/\$3\.34, \$3\.33, \$3\.33/);
 assert.match(STEPS[0].expected,/two no-shows.*need one extra fictional attendee/);
 assert.match(STEPS[3].expected,/Never retry an uncertain charge/);
 assert.match(STEPS[4].expected,/NOT provider availability/);
 assert.match(html,/checklist is only a navigation aid/i);
 assert.match(html,/resets on reload/);
 assert.match(html,/id="judge-copy-prompt"/);
 assert.match(html,/src="\/static\/judge_walkthrough\.js"/);
});
