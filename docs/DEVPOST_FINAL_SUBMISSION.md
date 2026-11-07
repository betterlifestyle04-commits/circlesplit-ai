# CircleSplit AI — PayPal AI Hackathon final submission handoff

**Status checked 7 November 2026 from the connected Devpost project:**
The CircleSplit AI project is **published** at
https://devpost.com/software/circlesplit-ai but the PayPal AI Hackathon
entry currently has **no recorded \`submitted_at\`**. The project has
**no \`video_url\`**. **Do not confuse a public project page with a
completed hackathon entry.**

**Deadline:** Thursday **12 November 2026, 20:00 UTC**
(**21:00 in Oslo/CET**). Submission was open at the time of inspection.
Target finishing the user-controlled recording and form by **11 November**,
leaving time for upload/playback or website issues.

Official competition:
https://paypalaihackathon.devpost.com/

## Non-negotiable deliverables

- [x] Public working demo: https://circlesplit-ai-demo.onrender.com/
- [x] Public reviewer walkthrough: https://circlesplit-ai-demo.onrender.com/judge
- [x] Public source, runnable setup and MIT license:
  https://github.com/betterlifestyle04-commits/circlesplit-ai
- [x] Source describes both Google Gemini AI and PayPal **Sandbox** Orders v2.
- [x] Public Devpost project page with technical write-up.
- [ ] **Record and publish a public YouTube demo shorter than 3:00.**
  Must show the functioning app on its actual target device, with Gemini
  AI and PayPal Sandbox meaningful use shown accurately.
- [ ] Add public YouTube URL to the project/submission, verify playback
  signed out, and inspect the full video for exposed private data.
- [ ] Complete **all mandatory Devpost questions**, including personal
  eligibility attestations only after the submitter has checked them.
- [ ] Give judges separate **restricted** integration-workspace credentials
  via Devpost's optional **testing instructions/credentials** field;
  do not place credentials in this public repo or video.
  Before submission, use the organizer-only **Check judge login expiry**
  control and verify that access covers the official judging end,
  **15 December 2026, 16:00 UTC**. Test a real judge login in incognito.
  Judge credentials cannot create/capture/reconcile PayPal Sandbox
  orders; the organizer-run video supplies that evidence.
- [ ] Click final **Submit** and independently confirm Devpost reports
  **Submitted** and/or the entry's \`submitted_at\` is populated.

For a local, no-network inspection run:
\`\`\`bash
python tools/submission_preflight.py
python tools/submission_preflight.py --video-url "https://youtu.be/REPLACE_WITH_11_CHAR_ID"
\`\`\`
The second command checks **URL format only**; it cannot attest that
the video is actually publicly visible or under 3 minutes. Even a
green local source check still requires personal Devpost form review
and an explicit final submission.

## Judging criteria: where to demonstrate evidence

Devpost lists **five criteria, each scored on a five-point scale**:

| Criterion | Show or substantiate | Avoid claiming |
|---|---|---|
| Technological Implementation | Real Gemini structured editable proposal; server-side PayPal Sandbox Orders v2 with approval, capture validation, idempotency and signed webhooks; tested exact-cent allocation | The public browser simulation itself performs provider requests |
| Design | Responsive public guest demo, Event Planner, what-if draft/comparison, private participant consent, distinct verified vs simulated statuses | A complete production account/payment platform |
| Potential Impact | Community sports, clubs and group organizers spend time reconciling ambiguous splits; demonstrate transparent budgeting and consent | Validated customer adoption or actual user happiness without evidence |
| Innovation/Idea | Combining AI suggestions, exact-cent splits, participant consent and safe Sandbox checkout; strict simulation/integration isolation | Escrow, disbursing group funds, or patented originality |
| Presentation | Under-3-minute functioning recording, clear problem/solution, live or previously recorded real Sandbox evidence, GitHub + demo links and caveats | Treating an order created or buyer return as verified payment |

The **Demo video** is required by the official contest. A source
repository and interactive website alone are not enough.

## Copy-ready project description (only use if it remains accurate)

### Inspiration

Group sports sessions and community events can be unnecessarily difficult
to organize: costs change, participants need to understand their share,
and an order-created notification should not be confused with payment
settlement. CircleSplit AI tests a clearer workflow for small groups.

### What it does

CircleSplit provides an event planner with equal and weighted exact-cent
USD splits, attendance/no-show scenarios, read-only alternative-budget
comparisons, participant-specific quoted shares, and explicit approval.
The open public guest experience is **fictional and stored only in the
visitor's browser**.

A separate protected integration workspace connects to **Google Gemini**
to turn a natural-language expense note into structured, editable proposals.
Organizers retain full control over whether to apply the suggestions.
**PayPal Sandbox Orders v2** supports a test-only flow for creating an
order, obtaining buyer approval, verifying a capture's amount and currency,
handling signed webhooks and reconciling uncertain outcomes.
A created order, buyer return, simulated contribution, and verified
Sandbox capture are distinct states.

### How it was built

Python/FastAPI, SQLite, vanilla HTML/CSS/JavaScript, Google Gemini,
PayPal Sandbox REST APIs, Render, and GitHub Actions. Core allocation
uses deterministic integer-cents, with a broad automated Python and
JavaScript regression suite. The repo is MIT licensed.

### Challenges and lessons

An ephemeral hosted demo can lose local test-ledger history; AI suggestions
must not trigger charges; payment retries after uncertain provider responses
can be unsafe. We introduced strict separation between public simulation
and protected provider operations, approval gates, capture verification,
recoverability diagnostics, and automated live release checks. These are
hackathon safeguards, not proof of production-grade durability or payment
risk management.

### Current limitations

The Render Free deployment uses **ephemeral SQLite**, no durable offsite
recovery, no account-grade identity verification, and no live-money
checkout. Test actions must use a PayPal **Sandbox personal buyer**.
Credentials must be sent only through a private judging channel.

## Devpost custom submission questions

These labels and internal IDs were retrieved from the official connected
Devpost submission requirements on 7 November 2026. Supply personal
information and subjective feedback yourself; don't publish those answers
in this public file.

| Field ID | Required field | Suggested preparation / action |
|---|---|---|
| 28778 | Submitter Type | Select **Individual** if submitting alone; otherwise select the truthful team/organization type |
| 28779 | Submitter Country of Residence | Select actual residence country |
| 28780 | If any team member resides in Canada, province | Enter **N/A** if nobody resides in Canada, per form instruction |
| 28781 | Organization Name | Enter **N/A** if not representing an organization, per form instruction |
| 28782 | New or existed before 1 October 2026, 9:15 PT | Confirm actual start date; the Devpost draft was created in November but that does not prove the concept did not predate October |
| 28783 | What changed if project existed earlier | **N/A** if truly new; otherwise describe genuine hackathon-period improvements |
| 28784 | Main PayPal and AI technology requirement | Use the technology explanation below; don't confuse the public demo with the protected integration |
| 28786 | Optional sponsor tool(s) | **Render** is used for hosting; verify the sponsor rules before selecting any other category |
| 28788 | Public code repository | https://github.com/betterlifestyle04-commits/circlesplit-ai |
| 28787 | Functional demo URL | https://circlesplit-ai-demo.onrender.com/ |
| 28798 | Testing instructions or credentials (optional field) | Include /judge link and private judge credentials *only* in this Devpost field, never public README/video |
| 28790 | PayPal integration experience (1–10) | Subjective; choose your own assessment |
| 28791 | Why you chose that experience rating | Describe genuine strengths, difficulties, documentation and API lessons |
| 28792 | Open to feedback contact | Choose **Yes** or **No** yourself |
| 28793 | APIMatic Context Plugin experience (optional) | Leave blank if not used |
| 28799 | AG Grid experience (optional) | Leave blank if not used |
| 28794 | Age / majority declaration | Check only if the assertion is true for you and any teammates |
| 28795 | Eligible Jurisdiction declaration | Check only if eligible under official rules |
| 28796 | Not affiliated with promotion entities declaration | Check only if true for you and teammates |
| 29053 | AI tools used | Name Google Gemini and describe implemented use; add any other tools used truthfully |
| 29054 | Level of learning | Choose **None**, **Moderate**, or **Significant** based on your experience |
| 29055 | AI career value | Choose **Yes** or **No** based on your own experience |

### Field 28784 — technology requirement (copy-ready)

CircleSplit AI meaningfully integrates **PayPal Sandbox REST APIs
(Orders v2)** and **Google Gemini**. Gemini extracts expenses,
candidate allocation strategy and a rationale from an organizer's
natural-language note; its output is validated and editable, and
requires explicit human approval before applying changes. Separately,
the protected CircleSplit workspace creates test-only PayPal orders
using server-side OAuth and idempotency keys, requires buyer approval,
verifies exact USD amount/currency and completed capture state, and
supports signed webhook and existing-order reconciliation. The public
no-login planner is a deliberately separate fictional simulation:
it makes no Gemini or PayPal requests and moves no real money.

### Field 29053 — AI tools used (copy-ready)

**Google Gemini (via Google Generative Language API)** powers
natural-language expense parsing and review-only budget suggestions
in the protected organizer workspace. AI output cannot initiate
payment or independently change the financial ledger. Mention any
other AI developer tools you personally used only if applicable.

### Optional field 28798 — non-secret skeleton

Start with https://circlesplit-ai-demo.onrender.com/judge .
The homepage provides a fully interactive fictional no-login demo.
For real **Gemini** integration and **read-only PayPal Sandbox ledger
inspection**, use the separate protected workspace at
https://circlesplit-ai-demo.onrender.com/workspace and time-limited
judge credentials supplied **privately in this field**. Copy the sample
expense note from /judge; test an editable $235 Gemini proposal and
inspect Activity for local payment states. **Judge credentials cannot
create, capture, or reconcile PayPal Sandbox orders.** These
organizer-only actions are demonstrated in the genuine under-three-minute
video; they require organizer credentials and a Sandbox personal buyer.
No live card or real-money payment is supported. An ORDER CREATED result
is not a VERIFIED CAPTURE. The shared testing database is temporary
and may reset.

**Insert actual authorized judge credentials only at submission time**,
not in the public repository, a public issue, or this template.

## Final checks just before clicking Submit

1. [ ] Incognito visit to / and /judge succeeds. The latest
   GitHub Actions deployment gate reports the live revision and
   protected workspace still requires Basic authentication.
2. [ ] YouTube demo plays **without login**, lasts strictly under
   3:00, shows actual software running, and discloses no credentials,
   invitation tokens, order IDs or personal buyer data.
3. [ ] Owner-only judge access readiness covers
   **15 December 2026, 16:00 UTC** and the separate login succeeds
   in an incognito browser. Provide credentials privately; ordinary
   public users do not get them. Judge access **cannot create, capture,
   or reconcile PayPal Sandbox orders**. Do not overstate what it permits.
4. [ ] Repository remains public with MIT LICENSE, setup instructions,
   implementation, and both technologies explained.
5. [ ] All required form fields are complete; country, team, age,
   eligibility and subjective feedback answers are truthful.
6. [ ] Final project entry submitted **before 12 November 20:00 UTC**.
7. [ ] Reopen Devpost and independently verify status **Submitted** or
   a non-null submission timestamp. Save a private screenshot or email
   confirmation; do not assume \`published\` means \`submitted\`.

**Do not delay final submission just to add features.** The existing
public demo, source repo, and technical testing are substantial; the
missing video and final form are the immediate dependencies.
