"use strict";
/*
 * Browser-local, privacy-minimal SQLite dataset continuity marker.
 * This is NOT a backup, browser security boundary, provider ledger, durable
 * audit or background monitor. It stores ONLY a truncated DB incarnation ID,
 * two aggregate counts and observation timestamp in the current browser.
 */
(function(root) {
  const KEY = "circlesplit:sandbox-continuity:v1";
  const MAX_SAVED_CHARS = 512;
  const EPOCH = /^[a-f0-9]{8}-[a-f0-9]{3}$/i;

  function validCount(n) {
    return Number.isSafeInteger(n) && n >= 0 && n <= 1_000_000_000;
  }
  function validTimestamp(s) {
    return typeof s === "string" && s.length >= 20 && s.length <= 40 &&
      /^\d{4}-\d{2}-\d{2}T/.test(s) &&
      Number.isFinite(Date.parse(s));
  }
  function snapshot(readiness, timestamp = new Date().toISOString()) {
    if (!readiness || typeof readiness !== "object" || Array.isArray(readiness) ||
        readiness.mode !== "sandbox-only" ||
        typeof readiness.storage_epoch !== "string" ||
        !EPOCH.test(readiness.storage_epoch) ||
        !validCount(readiness.current_store_verified_captures) ||
        !validCount(readiness.current_store_webhook_events) ||
        !validTimestamp(timestamp)) {
      throw Error("The protected dataset-check response is incomplete.");
    }
    return {
      version: 1,
      epoch: readiness.storage_epoch.toLowerCase(),
      captures: readiness.current_store_verified_captures,
      webhooks: readiness.current_store_webhook_events,
      observed_at: timestamp,
    };
  }
  function validCheckpoint(data) {
    return !!data && typeof data === "object" && !Array.isArray(data) &&
      Object.keys(data).length === 5 &&
      data.version === 1 && typeof data.epoch === "string" &&
      EPOCH.test(data.epoch) &&
      validCount(data.captures) && validCount(data.webhooks) &&
      validTimestamp(data.observed_at);
  }
  function usableStorage(storage) {
    try { return typeof storage==="function"?storage():storage; }
    catch (_) { return null; }
  }
  function load(storage) {
    try {
      if (!storage || typeof storage.getItem !== "function") return {state:"unavailable"};
      const raw=storage.getItem(KEY);
      if (raw === null) return {state:"empty"};
      if (typeof raw !== "string" || raw.length > MAX_SAVED_CHARS || !raw.length) {
        return {state:"invalid"};
      }
      const value=JSON.parse(raw);
      return validCheckpoint(value) ? {state:"stored",value} : {state:"invalid"};
    } catch (_) {
      return {state:"unavailable"};
    }
  }
  function save(storage, marker) {
    if (!validCheckpoint(marker)) return false;
    try {
      if (!storage || typeof storage.setItem !== "function") return false;
      storage.setItem(KEY, JSON.stringify(marker));
      return true;
    } catch (_) {
      return false;
    }
  }
  function assess(previous, current) {
    if (!validCheckpoint(current)) throw Error("Invalid current checkpoint.");
    if (previous === null) {
      return {kind:"first",concern:false};
    }
    if (!validCheckpoint(previous)) throw Error("Invalid previous checkpoint.");
    if (previous.epoch !== current.epoch) {
      return {kind:"new-dataset",concern:true};
    }
    if (current.captures < previous.captures ||
        current.webhooks < previous.webhooks) {
      return {kind:"count-regression",concern:true};
    }
    return {kind:"consistent",concern:false};
  }
  function newestCheckpoint(previous,current) {
    if (!validCheckpoint(previous) || !validCheckpoint(current) ||
        previous.epoch !== current.epoch) throw Error("Cannot merge different datasets.");
    return {
      ...current,
      captures:Math.max(previous.captures,current.captures),
      webhooks:Math.max(previous.webhooks,current.webhooks),
    };
  }

  function setup(doc, storage, fetchReadiness, confirmAction) {
    const get = id => doc.getElementById(id);
    const message=get("continuity-status");
    const banner=get("continuity-alert");
    const metadata=get("continuity-details");
    const checkButton=get("continuity-check");
    const acceptButton=get("continuity-acknowledge");
    if (!message || !banner || !metadata || !checkButton || !acceptButton) {
      throw Error("Dataset continuity controls are missing.");
    }
    let latest=null;
    let lastReport=null;
    let busy=false;
    function show(kind, current, previous) {
      const issue=kind==="new-dataset" || kind==="count-regression" ||
                  kind==="invalid";
      const status={
        first:"First observation saved in this browser. This is not an external backup.",
        consistent:"Same observed dataset; no aggregate count regression since this browser's checkpoint.",
        "new-dataset":"Potential database reset or replacement detected. Old local payment attempts may be missing.",
        "count-regression":"Recorded capture/webhook totals are lower than this browser previously observed.",
        invalid:"This browser's saved checkpoint is invalid. Continuity cannot be established.",
        unavailable:"Browser checkpoint storage is unavailable. No restart detection is available in this browser."
      };
      message.textContent=status[kind] || "Dataset continuity could not be checked.";
      if (current) {
        metadata.textContent="Current dataset ID: "+current.epoch+
          " · Current verified Sandbox captures: "+current.captures+
          " · Webhook events: "+current.webhooks+
          (previous?" · Previous dataset ID: "+previous.epoch+
            " · Previously observed captures: "+previous.captures+
            " · Webhook events: "+previous.webhooks:"");
      } else metadata.textContent="No current dataset observation.";
      if (issue) {
        banner.style.display="block";
        banner.textContent=(kind==="new-dataset" ?
          "Possible storage reset: the database identifier changed since this browser's previous observation. " :
          kind==="count-regression" ?
          "Possible data rollback: the database has fewer payment evidence records than previously observed. " :
          "Local dataset checkpoint is corrupt or unsupported. ") +
          "Do not assume missing records mean PayPal Sandbox never processed the orders. " +
          "Review saved reconciliation manifests and inspect the PayPal Sandbox account before starting another payment. " +
          "This browser cannot restore deleted records.";
      } else {
        banner.style.display="none";
        banner.textContent="";
      }
      acceptButton.disabled = busy || !issue || !current;
      return {kind,concern:issue};
    }
    function observe(readiness) {
      const current=snapshot(readiness);
      latest=current;
      const previous=load(usableStorage(storage));
      if (previous.state==="unavailable") {
        lastReport={kind:"unavailable",current,previous:null};
        return show("unavailable",current,null);
      }
      if (previous.state==="invalid") {
        lastReport={kind:"invalid",current,previous:null};
        return show("invalid",current,null);
      }
      if (previous.state==="empty") {
        const stored=save(usableStorage(storage),current);
        lastReport={kind:stored?"first":"unavailable",current,previous:null};
        return show(lastReport.kind,current,null);
      }
      const result=assess(previous.value,current);
      if (!result.concern) {
        const merged=newestCheckpoint(previous.value,current);
        if (!save(usableStorage(storage),merged)) {
          lastReport={kind:"unavailable",current,previous:previous.value};
          return show("unavailable",current,previous.value);
        }
      }
      lastReport={kind:result.kind,current,previous:previous.value};
      return show(result.kind,current,previous.value);
    }
    async function check() {
      if (busy) return;
      busy=true;checkButton.disabled=true;acceptButton.disabled=true;
      message.textContent="Checking protected dataset identity and aggregate counts…";
      let failed=false;
      try {
        observe(await fetchReadiness());
      } catch (_) {
        failed=true;
        message.textContent="Dataset check unavailable. The previous browser checkpoint was not changed.";
        // Never clear an existing warning because a network check failed.
        if(lastReport?.kind==="new-dataset" || lastReport?.kind==="count-regression" ||
           lastReport?.kind==="invalid") {
          banner.style.display="block";
        }
      } finally {
        busy=false;checkButton.disabled=false;
        if(!failed && lastReport) show(lastReport.kind,lastReport.current,lastReport.previous);
        if(failed) acceptButton.disabled=true;
      }
    }
    async function acknowledge() {
      if (busy || !lastReport ||
          !["new-dataset","count-regression","invalid"].includes(lastReport.kind)) {
        return;
      }
      const messageText="Only acknowledge after reviewing any saved private reconciliation "+
        "manifests and checking existing PayPal Sandbox orders externally. "+
        "This action replaces ONLY this browser's warning baseline. "+
        "It does not recover, delete, settle or prove any payment. Continue?";
      if (!confirmAction(messageText)) return;
      busy=true;checkButton.disabled=true;acceptButton.disabled=true;
      try {
        const latestServer=snapshot(await fetchReadiness());
        // A tab or server that changed after the earlier alert must be
        // inspected again. No stale checkmark may erase a newer warning.
        if (!latest || latestServer.epoch!==latest.epoch ||
            latestServer.captures!==latest.captures ||
            latestServer.webhooks!==latest.webhooks) {
          throw Error("The current dataset changed. Inspect the latest results first.");
        }
        const stored=load(usableStorage(storage));
        const old=lastReport.previous;
        if ((lastReport.kind==="invalid" && stored.state!=="invalid") ||
            (lastReport.kind!=="invalid" &&
             (stored.state!=="stored" || stored.value.epoch!==old.epoch ||
              stored.value.captures!==old.captures ||
              stored.value.webhooks!==old.webhooks))) {
          throw Error("The browser checkpoint changed in another tab.");
        }
        if (!save(usableStorage(storage),latestServer)) {
          throw Error("Browser storage rejected the new checkpoint.");
        }
        latest=latestServer;
        lastReport={kind:"consistent",current:latestServer,previous:latestServer};
        show("consistent",latestServer,latestServer);
        message.textContent="New browser baseline saved after manual acknowledgement. "+
          "This is NOT provider reconciliation or a restored payment ledger.";
      } catch(error) {
        message.textContent="Baseline not changed: "+error.message;
      } finally {
        busy=false;checkButton.disabled=false;
        if(lastReport) acceptButton.disabled =
          !["new-dataset","count-regression","invalid"].includes(lastReport.kind);
      }
    }
    checkButton.addEventListener("click",check);
    acceptButton.addEventListener("click",acknowledge);
    return {observe,check,acknowledge,latest:()=>latest,
            report:()=>lastReport};
  }

  const api={KEY,snapshot,validCheckpoint,load,save,assess,newestCheckpoint,setup};
  if (typeof module!=="undefined"&&module.exports) module.exports=api;
  else root.CircleSplitContinuity=api;
})(typeof window!=="undefined"?window:{});
