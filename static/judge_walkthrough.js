"use strict";
/* Public, browser-local judge navigator. No provider requests or credentials. */
(function(root) {
  const SAMPLE_PROMPT =
    "Our court costs $180, equipment $25 and refreshments $30. Twenty friends will attend.";
  const STEPS = Object.freeze([
    Object.freeze({
      id: "public", label: "Public simulation", title: "Explore the fictional planning demo",
      expected: "Try a $10 split among 3 people ($3.34, $3.33, $3.33). In the public Resilience lab, two no-shows from a $220 / 20-person group with a $12 cap need one extra fictional attendee. All contributions are SIMULATED.",
      href: "#judge-public", scope: "No account required"
    }),
    Object.freeze({
      id: "ai", label: "Gemini AI", title: "Review an editable AI proposal",
      expected: "Use the provided note. Expected identified expenses: $180 + $25 + $30 = $235. The organizer must choose whether to apply suggestions.",
      href: "#judge-ai", scope: "Private judge credentials"
    }),
    Object.freeze({
      id: "consent", label: "Participant consent", title: "Review private-link cost transparency",
      expected: "Generate a private invitation, check the fictional share, total budget, split method, and cost categories. Approval is not a charge.",
      href: "#judge-consent", scope: "Private participant link"
    }),
    Object.freeze({
      id: "paypal", label: "PayPal Sandbox", title: "Verify a completed test capture",
      expected: "Judge credentials can inspect the local Sandbox ledger and audits but cannot create, capture or reconcile PayPal test orders. Watch the organizer-run Sandbox demo video for actual provider evidence. Order created is not paid; look for VERIFIED CAPTURE, which may disappear from ephemeral storage after redeploy.",
      href: "#judge-paypal", scope: "Read-only judge view · Organizer-only Sandbox"
    }),
    Object.freeze({
      id: "evidence", label: "Evidence & limits", title: "Inspect evidence and engineering boundaries",
      expected: "Review the MIT source, automated tests, sandbox-only claims, and temporary SQLite storage. A healthy source revision is NOT provider availability.",
      href: "#judge-evidence", scope: "Public source and health check"
    })
  ]);

  function progress(marked) {
    const ids = new Set(STEPS.map(x => x.id));
    const completed = [...marked].filter(x => ids.has(x)).length;
    return { completed, total: STEPS.length, percent: Math.floor(100 * completed / STEPS.length) };
  }

  function verifiedPublicHealth(raw) {
    if (!raw || typeof raw !== "object" || raw.status !== "ok" ||
        raw.mode !== "sandbox-only" ||
        !(raw.git_commit === null || (typeof raw.git_commit === "string" &&
          /^[0-9a-f]{40}$/.test(raw.git_commit)))) {
      throw Error("Public health response did not match the expected sandbox-only format.");
    }
    return raw.git_commit;
  }

  async function checkPublicSource(fetchFn) {
    const response = await fetchFn("/health", {
      method: "GET", cache: "no-store", credentials: "omit",
      headers: { "Accept": "application/json" }
    });
    if (!response || !response.ok) throw Error("The public source-health endpoint is unavailable.");
    return verifiedPublicHealth(await response.json());
  }


  function runLocalMathChecks(math) {
    // Operates only on hard-coded fictional in-memory inputs; no fetch,
    // localStorage, participant tokens or external provider is involved.
    if (!math || typeof math.exactSplit !== "function" ||
        typeof math.preview !== "function") {
      throw Error("Local arithmetic module unavailable");
    }
    const participants = n => Array.from({length:n},(_,index)=>({
      id:index+10,weight:1
    }));
    const cases = [
      {
        id:"equal-cent-rounding",
        label:"$10 / 3 exact-cent allocation",
        evaluate(){
          const result=math.exactSplit(1000,participants(3),"equal");
          const correct=Array.isArray(result) && result.length===3 &&
            result[0]===334 && result[1]===333 && result[2]===333 &&
            result.reduce((a,b)=>a+b,0)===1000;
          return {correct,detail:correct?"$3.34 + $3.33 + $3.33 = $10.00":
            "Exact cents did not match the expected distribution"};
        }
      },
      {
        id:"volleyball-equal",
        label:"$220 / 20 volleyball budget",
        evaluate(){
          const result=math.exactSplit(22000,participants(20),"equal");
          const correct=Array.isArray(result) && result.length===20 &&
            result.every(v=>v===1100) &&
            result.reduce((a,b)=>a+b,0)===22000;
          return {correct,detail:correct?"20 × $11.00 = $220.00":
            "Volleyball allocation did not balance"};
        }
      },
      {
        id:"weighted-remainders",
        label:"Weighted largest-remainder allocation",
        evaluate(){
          const result=math.exactSplit(10001,[
            {id:10,weight:3},{id:11,weight:2},{id:12,weight:1}
          ],"weighted");
          const correct=Array.isArray(result) && result.length===3 &&
            result[0]===5000 && result[1]===3334 && result[2]===1667 &&
            result.reduce((a,b)=>a+b,0)===10001;
          return {correct,detail:correct?"$50.00 + $33.34 + $16.67 = $100.01":
            "Weighted shares or remainder allocation were inconsistent"};
        }
      },
      {
        id:"two-no-shows",
        label:"2 absences with a $12 share cap",
        evaluate(){
          const people=participants(20),snapshot=JSON.stringify(people);
          const result=math.preview({
            total_cents:22000,people,strategy:"equal",
            maximum_absent:5,max_share_cents:1200
          });
          const row=result?.projections?.[2];
          const correct=result.mode==="BROWSER_LOCAL_FICTIONAL_DEMO" &&
            result.read_only===true &&
            result.first_target_breach_at_absences===2 &&
            row?.absent_people===2 &&
            row?.largest_share_cents===1223 &&
            row?.minimum_replacements_needed===1 &&
            JSON.stringify(people)===snapshot;
          return {correct,detail:correct?"$12.23 largest share; 1 fictional replacement":
            "Attendance simulation or read-only invariant differed"};
        }
      },
      {
        id:"five-no-shows",
        label:"5 absences with a $12 share cap",
        evaluate(){
          const people=participants(20),snapshot=JSON.stringify(people);
          const result=math.preview({
            total_cents:22000,people,strategy:"equal",
            maximum_absent:5,max_share_cents:1200
          });
          const row=result?.projections?.[5];
          const correct=result.mode==="BROWSER_LOCAL_FICTIONAL_DEMO" &&
            result.read_only===true &&
            row?.absent_people===5 && row?.largest_share_cents===1467 &&
            row?.minimum_replacements_needed===4 &&
            JSON.stringify(people)===snapshot;
          return {correct,detail:correct?"$14.67 largest share; 4 fictional replacements":
            "Five-absence response or read-only invariant differed"};
        }
      }
    ];
    const checks=cases.map(check=>{
      try {
        const result=check.evaluate();
        return {id:check.id,label:check.label,
          passed:result.correct===true,detail:result.detail};
      } catch (_err) {
        return {id:check.id,label:check.label,passed:false,
          detail:"Calculation unavailable or returned an invalid result"};
      }
    });
    const passed=checks.filter(check=>check.passed).length;
    return {
      mode:"BROWSER_LOCAL_MATH_CHECKS",
      total:checks.length,passed,success:passed===checks.length,checks,
      notice:"Fictional browser math only. No server, Gemini or PayPal verification."
    };
  }

  function formatLocalMathReport(report) {
    // Accept only results with a consistent count. Never turn a failure
    // into an apparently successful copyable report.
    if (!report || report.mode !== "BROWSER_LOCAL_MATH_CHECKS" ||
        !Array.isArray(report.checks) || report.total !== 5 ||
        report.checks.length !== report.total ||
        !Number.isSafeInteger(report.passed)) {
      throw Error("No valid local arithmetic report");
    }
    const lines = report.checks.map(check => {
      if (!check || typeof check.passed !== "boolean" ||
          typeof check.label !== "string" || typeof check.detail !== "string") {
        throw Error("Invalid local arithmetic check");
      }
      return (check.passed ? "PASS" : "FAIL") + " — " +
        check.label + ": " + check.detail;
    });
    const actualPassed = report.checks.filter(check => check.passed).length;
    if (report.passed !== actualPassed ||
        report.success !== (actualPassed === report.total)) {
      throw Error("Inconsistent local arithmetic report");
    }
    return [
      "CircleSplit AI — browser-local arithmetic report",
      "Result: " + (report.success ? "PASS" : "FAIL") +
        " (" + report.passed + "/" + report.total + ")",
      ...lines,
      "",
      "Scope: Fictional browser-only exact-cent and no-show calculations.",
      "No server checks, Gemini calls, PayPal operations, captures or payment verification.",
      "This report does not prove deployment health or organizer/participant authentication."
    ].join("\n");
  }

  function setupJudgeUI(doc, fetchFn, clipboard, math) {
    const $ = id => doc.getElementById(id);
    const navigation = [...doc.querySelectorAll("[data-judge-step]")];
    const view = {
      title: $("judge-current-title"), scope: $("judge-current-scope"),
      expected: $("judge-current-expected"), progressText: $("judge-progress-text"),
      progressBar: $("judge-progress-bar"), review: $("judge-review-toggle"),
      previous: $("judge-prev"), next: $("judge-next"),
      detail: $("judge-step-detail"), status: $("judge-status"),
      check: $("judge-source-check"), health: $("judge-source-status"),
      copy: $("judge-copy-prompt"),
      mathButton: $("judge-run-local-tests"),
      mathStatus: $("judge-math-status"),
      mathResults: $("judge-math-results"),
      copyMath: $("judge-copy-math-report"),
      copyMathStatus: $("judge-copy-math-status")
    };
    if (navigation.length !== STEPS.length ||
        Object.values(view).some(value => !value)) {
      throw Error("The judge navigation is incomplete.");
    }

    let current = 0;
    let lastHealthCommit = null;
    let latestMathReport = null;
    view.copyMath.disabled = true;
    const reviewed = new Set();
    const render = () => {
      const step = STEPS[current];
      for (const button of navigation) {
        const isCurrent = button.getAttribute("data-judge-step") === step.id;
        button.setAttribute("aria-current", isCurrent ? "step" : "false");
        button.classList.toggle("selected", isCurrent);
        const done = reviewed.has(button.getAttribute("data-judge-step"));
        button.classList.toggle("done", done);
      }
      view.title.textContent = step.title;
      view.scope.textContent = step.scope;
      view.expected.textContent = step.expected;
      view.detail.setAttribute("href", step.href);
      view.review.textContent = reviewed.has(step.id) ? "Mark as not reviewed" : "Mark step reviewed";
      view.previous.disabled = current === 0;
      view.next.disabled = current === STEPS.length - 1;
      const done = progress(reviewed);
      view.progressText.textContent = done.completed + " of " + done.total +
        " steps marked reviewed in this page (not submitted or saved)";
      view.progressBar.style.width = done.percent + "%";
    };
    navigation.forEach(button => button.addEventListener("click", () => {
      const index = STEPS.findIndex(x => x.id === button.getAttribute("data-judge-step"));
      if (index !== -1) { current = index; render(); }
    }));
    view.review.addEventListener("click", () => {
      const key = STEPS[current].id;
      if (reviewed.has(key)) reviewed.delete(key);
      else reviewed.add(key);
      view.status.textContent = "Checklist is a personal navigation aid, not a test result or submission confirmation.";
      render();
    });
    view.previous.addEventListener("click", () => {
      if (current > 0) { current -= 1; render(); }
    });
    view.next.addEventListener("click", () => {
      if (current < STEPS.length - 1) { current += 1; render(); }
    });
    view.mathButton.addEventListener("click", () => {
      view.mathButton.disabled=true;
      view.copyMath.disabled=true;
      view.copyMathStatus.textContent="Not copied. Rechecking fictional arithmetic…";
      latestMathReport=null;
      try {
        const report=runLocalMathChecks(math);
        latestMathReport=report;
        view.copyMath.disabled=false;
        view.copyMathStatus.textContent="Report ready to copy, including any failed checks.";
        view.mathStatus.textContent=report.success ?
          "PASS: "+report.passed+"/"+report.total+
          " browser-only math checks passed. No network, Gemini or PayPal calls." :
          "FAIL: "+report.passed+"/"+report.total+
          " browser-only math checks passed. Review the failed tests below.";
        view.mathResults.textContent=report.checks.map(check=>
          (check.passed?"PASS":"FAIL")+" — "+check.label+": "+check.detail
        ).join("\n");
      } catch (_err) {
        view.mathStatus.textContent=
          "UNAVAILABLE: Public arithmetic code could not be loaded. No payment or server tests were run.";
        view.mathResults.textContent="";
        view.copyMathStatus.textContent="No valid report to copy; arithmetic code unavailable.";
      } finally {
        view.mathButton.disabled=false;
      }
    });
    view.copyMath.addEventListener("click", async () => {
      if (!latestMathReport) {
        view.copyMathStatus.textContent="Run the local math checks before copying.";
        return;
      }
      try {
        if (!clipboard || typeof clipboard.writeText !== "function") {
          throw Error("Clipboard unavailable");
        }
        const reportText=formatLocalMathReport(latestMathReport);
        await clipboard.writeText(reportText);
        view.copyMathStatus.textContent="Copied actual browser-only pass/fail results and limitations.";
      } catch (_err) {
        view.copyMathStatus.textContent="Copy unavailable. Select the visible results manually.";
      }
    });
    view.copy.addEventListener("click", async () => {
      try {
        if (!clipboard || typeof clipboard.writeText !== "function") {
          throw Error("Clipboard permission is not available in this browser.");
        }
        await clipboard.writeText(SAMPLE_PROMPT);
        view.status.textContent = "Sample Gemini expense note copied. No AI request was made.";
      } catch (_) {
        view.status.textContent = "Could not copy. Select the example note in step 2 manually.";
      }
    });
    view.check.addEventListener("click", async () => {
      view.check.disabled = true;
      view.health.textContent = "Checking public source revision only…";
      try {
        const commit = await checkPublicSource(fetchFn);
        let msg = commit ?
          "Public source is responding: revision " + commit.slice(0, 12) + ". " :
          "Public source is responding, but no deploy revision was reported. ";
        if (commit && lastHealthCommit && lastHealthCommit !== commit) {
          msg += "Revision changed since this tab's previous check; demo data may have reset. ";
        }
        if (commit) lastHealthCommit = commit;
        view.health.textContent = msg +
          "This does NOT test Gemini, PayPal, judge login, or payment storage.";
      } catch (_) {
        view.health.textContent = "Public source check unavailable. This does not imply a payment failed; inspect existing sandbox orders manually.";
      } finally {
        view.check.disabled = false;
      }
    });
    render();
    return { progress: () => progress(reviewed), currentStep: () => STEPS[current].id };
  }

  const api = { STEPS, SAMPLE_PROMPT, progress, verifiedPublicHealth,
                checkPublicSource, runLocalMathChecks, formatLocalMathReport, setupJudgeUI };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else {
    root.CircleSplitJudge = api;
    if (root.document) setupJudgeUI(root.document, root.fetch.bind(root),
      root.navigator && root.navigator.clipboard, root.CircleSplitPublicRecovery);
  }
})(typeof window !== "undefined" ? window : {});
