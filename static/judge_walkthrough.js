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
      expected: "Use ONLY a PayPal Sandbox personal buyer account. Order created is not paid; look for VERIFIED CAPTURE. Never retry an uncertain charge.",
      href: "#judge-paypal", scope: "Private workspace + sandbox buyer"
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

  function setupJudgeUI(doc, fetchFn, clipboard) {
    const $ = id => doc.getElementById(id);
    const navigation = [...doc.querySelectorAll("[data-judge-step]")];
    const view = {
      title: $("judge-current-title"), scope: $("judge-current-scope"),
      expected: $("judge-current-expected"), progressText: $("judge-progress-text"),
      progressBar: $("judge-progress-bar"), review: $("judge-review-toggle"),
      previous: $("judge-prev"), next: $("judge-next"),
      detail: $("judge-step-detail"), status: $("judge-status"),
      check: $("judge-source-check"), health: $("judge-source-status"),
      copy: $("judge-copy-prompt")
    };
    if (navigation.length !== STEPS.length ||
        Object.values(view).some(value => !value)) {
      throw Error("The judge navigation is incomplete.");
    }

    let current = 0;
    let lastHealthCommit = null;
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
                checkPublicSource, setupJudgeUI };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else {
    root.CircleSplitJudge = api;
    if (root.document) setupJudgeUI(root.document, root.fetch.bind(root),
      root.navigator && root.navigator.clipboard);
  }
})(typeof window !== "undefined" ? window : {});
