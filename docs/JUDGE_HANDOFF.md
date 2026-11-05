# CircleSplit AI — Judge handoff

## Public entry points
- Public interactive guest experience: https://circlesplit-ai-demo.onrender.com/
- Public judge guide: https://circlesplit-ai-demo.onrender.com/judge
- Protected live Gemini and PayPal sandbox workspace: https://circlesplit-ai-demo.onrender.com/workspace
- Source code and automated tests: https://github.com/betterlifestyle04-commits/circlesplit-ai

The public homepage is a browser-local simulation. Only the protected workspace connects to the actual Gemini model and PayPal SANDBOX.

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

Before PayPal Sandbox checkout: In **Contributions**, select
**Check readiness** on the fictional participant. The read-only preflight
should explain missing approval, declined RSVP, an already-started order, or
any inconsistent share allocation. After approving an unchanged share,
**PayPal test** repeats readiness checks, requests explicit confirmation,
and creates a new sandbox-only order if locally eligible. It cannot confirm
provider availability or settlement. Never retry an uncertain creation
response; inspect Activity and PayPal Sandbox instead.

When PayPal Sandbox returns to the workspace, CircleSplit checks the
**existing** order. A return does not automatically capture funds. If
PayPal reports `APPROVED`, the organizer may explicitly confirm the
test capture; the server independently rechecks the provider order and
exact amount before attempting it. If the result is ambiguous, use
Activity → Check PayPal and investigate the original order. Never try a
second capture merely because an earlier screen timed out.

PayPal: Make a fresh fictional event costing $11.00 USD with one participant. Approve the share; select PayPal test. Use a *PayPal SANDBOX personal buyer account* obtained from PayPal Developer Dashboard (never a live PayPal account or real card). Complete checkout; on return, CircleSplit should show VERIFIED CAPTURE under Activity. If the flow is interrupted, use Activity → Check PayPal to resume or reconcile the *existing order*, not create duplicates.

The test environment is sandbox only. The protected integration workspace uses shared fictional data and temporary SQLite storage; it may reset after deployment. If judges prefer not to use a sandbox buyer account, the under-3-minute YouTube video documents our confirmed capture and the repository contains the integration and tests.

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
- Complete a PayPal sandbox checkout once, confirm VERIFIED CAPTURE and successful webhook response.
- Record a **public YouTube demo video under 3 minutes** (no visible credentials or buyer details).
- Confirm the public repository includes the MIT license and setup instructions.
- Complete required Devpost submission questions truthfully.
- Paste judge credentials only in the private testing-instructions field during submission.

**Do not commit secrets to GitHub.**
