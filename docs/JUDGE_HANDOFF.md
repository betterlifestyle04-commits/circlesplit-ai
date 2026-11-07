# CircleSplit AI — Judge handoff

## Public entry points
- Public interactive guest experience: https://circlesplit-ai-demo.onrender.com/
- Public judge guide: https://circlesplit-ai-demo.onrender.com/judge
- Protected live Gemini and PayPal sandbox workspace: https://circlesplit-ai-demo.onrender.com/workspace
- Source code and automated tests: https://github.com/betterlifestyle04-commits/circlesplit-ai

The public homepage is a browser-local simulation. Only the protected workspace connects to actual Gemini and PayPal SANDBOX. **A time-limited judge login can inspect plans, run Gemini review, simulate contributions and view local ledger/audits; it cannot create, capture, or reconcile real PayPal Sandbox test orders.** Those actions require the separate organizer login. Public demo and owner-only test evidence must never be confused.

## Optional protected affordability demonstration

After signing into the organizer workspace, select the seeded fictional
event and open **Scenario Lab → Affordability target**. Set the per-person
limit to **$10.00**, allow up to **5 additional fictional attendees** and
choose **equal split**. The server should recommend **2 additional
participants**, giving a hypothetical 22-person group with each person's
share no more than $10.00 for the $220 event. Try weighted split or a very
low cap to see an explicit no-solution result. Results are read-only and
do **not** change current approvals, participation, or any PayPal order.

## Guided browser walkthrough (no credentials)

Open the public [judge guide](https://circlesplit-ai-demo.onrender.com/judge)
for a five-step interactive navigation panel. Its progress labels are
page-local **manual checkmarks**, not automated assertions or submission
confirmation, and reset on page reload. Every stage has a link to its
detailed testing instructions. Judges can copy the fictional Gemini example
to the clipboard and request one public source-health check. The health
result only identifies a running application revision, not current
PayPal/Gemini connectivity, data durability, buyer approval, or capture.

The **public** planning example has a $10 fictional budget shared among
three people, allocated as $3.34, $3.33, and $3.33, in exact cents.
Private invitation consent should be tested with fictional data; never put
bearer invitations in public issue comments or test recordings.


**Never put judge passwords in this public file, the project description or the YouTube video.**

Use the following instructions in the private judge-testing field after entering separate judge credentials:

CircleSplit has a public interactive simulation (no login) and a separate protected integration workspace. Start at https://circlesplit-ai-demo.onrender.com/judge. Then sign into https://circlesplit-ai-demo.onrender.com/workspace using the judge username/password provided separately in this private field.

AI: Open AI assistant and submit: "Our court costs $180, equipment $25 and refreshments $30. Twenty friends will attend." Gemini should extract three editable amounts totalling $235 USD with a rationale. The organizer must explicitly approve each proposal before applying it.

Participant consent: For any event with participants and expenses, generate
an individual private invitation in the organizer workspace. Opening the link
shows the invited person's fictional share, total planned budget, equal or
weighted split method, and aggregate cost categories. Check that the private
view reveals no other person's name or share. Approving the quoted amount
records consent only: it does not initiate PayPal or move money.

PayPal review **using judge credentials**: open **Activity** and inspect the
read-only payment ledger and local signed-webhook audit. Distinguish
**VERIFIED CAPTURE** (test provider capture verified), **ORDER CREATED —
NOT PAID** (no capture), and **SIMULATED** (fictional only). The judge
login intentionally cannot use **PayPal test**, **Check PayPal**, create
an order, capture, or reconcile. Do **not** tell judges to make a new
Sandbox payment under the judge password: the server returns HTTP 403.

For actual Sandbox integration evidence, watch the public, authentic,
**under-three-minute demo video** showing an **organizer-initiated**
$11.00 fictional order, PayPal SANDBOX personal buyer approval and a
verified capture. The owner—not the judge—may reproduce that flow with
organizer credentials and a separate Sandbox personal buyer. A Sandbox
buyer account is never a live PayPal account or real payment card.
If an order is uncertain, do not retry creation or capture; the owner
must investigate the existing order in PayPal's Sandbox and Activity.

**Current database note:** Render Free uses ephemeral SQLite. Earlier
verified $11.00 test evidence from November 3 can disappear after
redeploy, so a missing current capture count cannot be treated as proof
of a failed past test. The video must be recorded from genuine provider
output; a simulated or recreated UI state is insufficient.

The test environment is sandbox only. The protected integration workspace uses shared fictional data and temporary SQLite storage; it may reset after deployment. If judges prefer not to use a sandbox buyer account, the under-3-minute YouTube video documents our confirmed capture and the repository contains the integration and tests.

## Judge login validity through the December judging window

The official judging window ends **15 December 2026 at 16:00 UTC**.
Before submitting, sign into the protected workspace with the organizer
login and select **Check judge login expiry**. The owner-only
`GET /api/judge-access-readiness` endpoint checks the separate judge
username/password **configuration** (without revealing values), whether
the login is enabled, and whether its timezone-aware expiry covers the
judging period. It cannot prove the login works, so separately sign
in with judge credentials in an incognito window to verify the actual
read-only experience. Configure `JUDGE_ACCESS_ENABLED`,
`JUDGE_USERNAME`, `JUDGE_PASSWORD`, and
`JUDGE_ACCESS_EXPIRES_AT` as **Render secrets**, not GitHub files.

Do **not** disable the owner-only payment boundary to make the judge
demo easier. Provide prior genuine Sandbox evidence through the public
YouTube demo and permit read-only inspection with judge credentials.

## Secrets and credential handling
- The judge workspace password must be supplied to judges **privately**, e.g. in Devpost's optional "Testing instructions or credentials" submission field, not in public repositories.
- PayPal sandbox buyer credentials are different from CircleSplit judge credentials; never expose live financial or private personal-account credentials.
- Store API keys in Render secret environment variables only.
- Judge access expires via JUDGE_ACCESS_EXPIRES_AT; owner access remains independent.
- The initial $11 sandbox capture was verified on November 3, 2026; it is not a real payment or revenue, and temporary transaction records may disappear on redeploy.

## Before submission
- Verify the public /judge page works without a password.
- Verify the separate judge login in an incognito window.
- Run the Gemini extraction once.
- With organizer credentials, complete a genuine PayPal Sandbox checkout once for the private demonstration footage; verify VERIFIED CAPTURE and preserve the video. The separate judge login intentionally cannot initiate this operation.
- Confirm `/api/judge-access-readiness` reports a judge expiry covering **15 December 2026, 16:00 UTC**, and separately test the judge login in an incognito window.
- Record a **public YouTube demo video under 3 minutes** (no visible credentials or buyer details).
- Confirm the public repository includes the MIT license and setup instructions.
- Complete required Devpost submission questions truthfully.
- Paste judge credentials only in the private testing-instructions field during submission.

**Do not commit secrets to GitHub.**
