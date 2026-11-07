# CircleSplit AI — recordable 2:45 PayPal AI Hackathon demo

**Status: recording not yet provided.** The contest requires a **public
YouTube video shorter than 3:00** which shows a working project, not
a slide deck or static mockup. The final link must be entered on Devpost
and verified from a signed-out browser before submission.

Target finished length **2:40–2:45**, leaving a margin for YouTube
duration rounding. Screen-record the actual browser UI. This is an
editing/filming plan, not evidence that the video has already been made.

## Before recording: secure, repeatable setup

1. Open the public demo: https://circlesplit-ai-demo.onrender.com/
   and private judge guide: https://circlesplit-ai-demo.onrender.com/judge .
2. Test the protected organizer workspace separately with **owner**
   credentials (never show login typing or a password manager).
   The separate judge credentials are intentionally prohibited from
   creating, capturing, or reconciling PayPal Sandbox test orders.
   Before submission use **Check judge login expiry** under the owner
   login, confirm access covers the end of judging on
   **15 December 2026, 16:00 UTC**, and separately test judge login
   in incognito. Do not film either credential.
3. Validate that Gemini is configured and successfully returns an
   editable proposal from the exact fictional example in the guide:
   **court $180, equipment $25, refreshments $30, total $235**.
4. For real integration footage, use a **PayPal Sandbox personal buyer**,
   never a live PayPal account. Complete the Sandbox $11.00 example on
   fictional data, then verify a **VERIFIED CAPTURE** row in Activity.
   Do not start a duplicate payment if any earlier request is uncertain.
5. Prepare or record safe footage of the **completed** test flow *before*
   editing. Crop out or redact every password, buyer email, order/capture
   token, private invitation bearer link, and payment return query.
   Do not blur a live interaction after sharing an unredacted clip.
6. In the final edit, show the public source and README/LICENSE.
   Use original narration and visuals, no third-party copyrighted audio.

## Time-coded screen plan and narration

| Time | Screen actions and evidence | Suggested spoken narration |
|---|---|---|
| **00:00–00:15** | Public homepage, visible PUBLIC DEMO label, event overview | "Group activities should be about playing, learning and connecting, not chasing unclear payments. CircleSplit helps organizers budget together and make everyone's share transparent." |
| **00:15–00:40** | Event Planner seeded volleyball **$220 / 20**. Show **$11 each**, switch weighted and back, open **Duplicate as what-if draft** and **Compare two fictional plans** | "The public interactive demo uses fictional data entirely in your browser. Equal and weighted allocations work in integer cents, and what-if drafts let you compare plans without rewriting an event's simulated history." |
| **00:40–01:12** | Protected workspace already authenticated. Open AI assistant; paste note; submit to **real Gemini**; show returned expense suggestions **$180, $25, $30 = $235** and human review buttons | "In the protected integration workspace, Gemini turns natural-language notes into structured expense suggestions. Every amount is reviewable. AI cannot approve an event or initiate a payment." |
| **01:12–01:35** | Existing or fresh fictional $11 event and private participant cost/consent preview; show share approval and checkout readiness | "Participants see their own proposed share and cost breakdown before consenting. An approval is not a charge. A separate readiness check blocks invalid or duplicated test checkout attempts." |
| **01:35–02:24** | Safe recording of **actual PayPal Sandbox checkout**: show sandbox domain and sandbox buyer approval without credentials; show return to workspace and **Activity: VERIFIED CAPTURE** | "CircleSplit integrates PayPal Sandbox Orders v2. It creates a test order with server-side amount checks, waits for buyer approval, and validates the completed capture. Order created or a browser redirect is not evidence of settlement. Only verified Sandbox captures are recorded as such." |
| **02:24–02:45** | /judge walkthrough, GitHub repo, MIT LICENSE, GitHub Actions green | "The open-source repository includes the setup, tests and automated release checks. The hosted database is temporary, and no real funds move. CircleSplit is a hackathon prototype that connects AI suggestions with accountable, test-only group payments." |

**Timing is a target; finish under 2:59.** Cut nonessential loading,
typing and login screens. Avoid speeding up the required provider proof
so much that a judge cannot read the real status.

## Video quality and authenticity checks

- Record the **functioning browser application** in 1080p landscape
  if practical; move the cursor slowly and use legible zoom.
- Keep "SIMULATED", "PayPal Sandbox", "ORDER CREATED" and
  "VERIFIED CAPTURE" visible when discussing those states. Do not
  mislabel simulated contributions as provider captures.
- Clearly distinguish **real, controlled Gemini/Sandbox calls** in the
  protected workspace from the **browser-local public simulation**.
- If a fresh provider call fails, **do not fabricate successful output**.
  You may show a genuine earlier captured test on screen if available,
  labeled as previously verified evidence, and be accurate about what
  worked and what was not rerun.
- No on-screen personal buyer credentials, real card details, private
  participant links, API keys, PayPal order IDs or access tokens.
- Use original sound only or licensed assets; don't include unlicensed
  sponsor logos or copyrighted music.
- Upload to **YouTube Public** (not Private or Unlisted if a public video
  is required). Open the link in a signed-out private window, verify
  playback, actual length under 3 minutes and clean captions.

## After upload

1. Copy the **public** YouTube link, and inspect it with:
   \`python tools/submission_preflight.py --video-url "<PUBLIC_YOUTUBE_URL>"\`
   (only tests URL format and repository files).
2. Add the video to the existing CircleSplit Devpost project and its
   PayPal AI Hackathon submission.
3. Finish every required custom field (see
   [DEVPOST_FINAL_SUBMISSION.md](DEVPOST_FINAL_SUBMISSION.md)).
4. Click **Submit**, then verify a real submission timestamp or
   Devpost **Submitted** state. A published project page is not enough.

**Deadline:** 12 November 2026, **20:00 UTC / 21:00 Oslo time**.
