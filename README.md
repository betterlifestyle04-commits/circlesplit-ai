# CircleSplit AI

AI-assisted group budgeting with participant approval and PayPal Sandbox checkout.

> **Hackathon development build. No real money movement.** This project is not production-ready and must not be publicly deployed without authentication, rate limits, and credential review.

**Devpost draft:** https://devpost.com/software/circlesplit-ai

## What it does
- Organizer creates an event, records expenses and participants.
- Deterministic integer-cent allocation makes equal or weighted shares add up to the exact event total.
- Participants explicitly approve their shares.
- PayPal Orders v2 **sandbox** can create and capture test payments after server-side amount validation.
- Sandbox transactions are kept distinct from clearly labeled simulated payments.
- Optional Gemini expense parser proposes a structured budget, subject to organizer approval.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate  # Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m pytest -q
uvicorn app:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. Test credentials go in server environment variables, **never GitHub**.

## Configuration

| Environment variable | Purpose |
| --- | --- |
| `PAYPAL_CLIENT_ID` | Sandbox REST app client ID |
| `PAYPAL_CLIENT_SECRET` | Sandbox REST app secret (server only) |
| `PAYPAL_WEBHOOK_ID` | Sandbox webhook verification |
| `PUBLIC_BASE_URL` | HTTPS URL for PayPal approval return |
| `GEMINI_API_KEY` | Optional AI expense extraction |
| `GEMINI_MODEL` | Optional model name |
| `CIRCLESPLIT_DB` | Optional SQLite database path |

Use sandbox buyer/business accounts from https://developer.paypal.com/dashboard/.

## Repository guide

- `app.py`: FastAPI API and local persistence
- `domain.py`: cent-exact allocation
- `paypal.py`: sandbox-only PayPal requests
- `static/`: responsive web dashboard
- `tests/`: backend tests
- `.github/workflows/ci.yml`: automated tests

## Advisory spending targets and contingency forecasts

- The **Events** page supports a per-event optional spending ceiling and **0–50% contingency reserve**. The organizer can preview an over-target amount, remaining headroom and projected total before saving.
- All forecasting is done in **integer cents**, with the contingency rounded **up** to the next cent so the risk buffer is not understated. A reserve is **hypothetical**: it is not added to expenses, allocated among participants, charged through PayPal, or presented as money collected.
- The planning ceiling is **advisory, not enforced**. Expenses may exceed the target; the dashboard clearly flags overruns rather than silently blocking an event or adjusting approved shares.
- The protected **Insights** page aggregates the number of targeted and over-target events, the combined hypothetical reserve and projected planned spending across the organizer's event list. Overrun totals are summed *per event* and are not netted against unrelated events' unused limits.
- Budget targets may be updated after a simulated or PayPal sandbox contribution without modifying existing financial records, consent links or captures. Changes create a privacy-minimal history entry, while exact repeats do not create duplicate history entries.
- A new `event_planning` SQLite table stores this information and is safely created alongside existing tables on application startup. Duplicating an event carries over planning preferences but never payments or approvals.
- Protected `GET /api/events/{eid}/planning` and `PUT /api/events/{eid}/planning` endpoints provide exact-cent planning data. The same forecast is included in `/api/state` to avoid extra calls.
- Node and Python tests cover rounding, invalid inputs, cloning, access control, idempotent history, live budget updates and strict financial separation.
- **Sandbox limitation:** These preferences remain subject to Render Free's ephemeral SQLite and may disappear after a deploy. They are planning aids, not actual expenses, guarantees of venue prices, payments or invoices.

## Planned expense categories & budget insights

- Each event expense can now be assigned one of six **validated** planning categories: **Venue & space, Equipment, Food & drinks, Travel, Services, and Other**.
- The protected **Events** page shows a category breakdown and lets an organizer change an existing expense's category. **Reclassification changes only metadata**: the budget, assigned shares, outstanding RSVP links and existing approvals do not change. To preserve auditability, category edits are blocked once a PayPal sandbox checkout or simulated contribution has locked the budget.
- The **Insights & exports** page shows cross-event category breakdowns and downloads a **planned expense category CSV**. CSV cells use the existing spreadsheet formula-injection protection.
- Gemini expense-extraction now includes a reviewable category suggestion. Invalid provider categories are downgraded to **Other**; organizers can edit categories before approving the proposal. Gemini never directly updates budget records or authorizes payments.
- Old expense records are migrated with the default **Other** category. New demo seed expenses are categorized for demonstration. Duplicating events preserves their categories but does not transfer prior approvals or payment records.
- The API provides a protected read-only `GET /api/events/{id}/budget-breakdown` and a guarded `PATCH /api/events/{id}/expenses/{expense_id}/category`.
- Automated Python and Node tests cover exact-cent category totals, a legacy-database upgrade, cloned expenses, budget locks, provider validation and the category CSV helper.
- Categories describe **planned costs**, not settled bills, invoices, merchant payouts or verified PayPal activity. All provider payments remain sandbox-only.

## Event finder, exact-cent split explanations and ledger-backed totals

- A searchable **Event directory** in the protected workspace filters upcoming, past and events needing attention, sorts by date or budget, and offers one-click selection of an event. This does not move or delete event data.
- Every participant row includes **Explain**: a local, read-only breakdown of their assigned share, effective weight, total event weight, floor allocation, and any one-cent largest-remainder adjustment. Ties are broken by stable participant ID, consistent with the server's allocation algorithm. If stored shares disagree, the panel warns the organizer to review event integrity.
- **Critical accounting hardening:** the backend's `sandbox_cents` and all derived funding KPIs now sum only local payment rows marked `completed` **with non-empty capture identifiers**. An isolated `sandbox_paid` participant status is no longer counted as verified sandbox funding.
- This is still confirmation within the local sandbox ledger, **not a real-time PayPal provider check or real-money transfer**. The dedicated owner-initiated order-status action remains available for provider reconciliation.
- Improved keyboard focus styling, reduced-motion support and horizontal scrolling for dense tables on narrow screens.
- Node tests cover directory filters and exact-cent explanations; Python regression tests verify that status-only flags and pending or capture-less payment rows do not inflate verified totals.

## Event History & Integrity (sandbox-only)

The protected organizer workspace now includes **History & checks**, with a chronological record of key operations and a read-only consistency report for the currently selected fictional event.

- Records event creation/duplication; expense and allocation changes; participant imports, approvals, invitations and RSVP responses; checklist actions; simulated contributions; PayPal sandbox order creation and *verified* captures.
- Entries use **fixed descriptions and restricted metadata** (IDs, counts, cents, enum states) and do **not** contain participant names, invitation secrets, API credentials, PayPal order IDs, capture IDs, or webhook IDs. The workspace allows a CSV download of this limited history.
- The consistency report checks exact-cent allocation totals, missing participants, inconsistent local completed-capture statuses, incomplete capture identifiers, payment amount mismatches, unexpected simulated/payment conflicts, duplicate orders and declined-but-unpaid approvals.
- Pending sandbox checkout orders are displayed separately as **pending**, not as captured payments or necessarily as consistency errors.
- Capture history records are emitted only once when a payment transitions to `completed` in local SQLite. Verified webhook replay or repeated capture calls do not create duplicate completion entries. Failed mutations never add an audit entry because changes and history use the same SQLite transaction.
- **Not tamper-proof.** This is a limited in-database history, not a production financial audit log. Records from before the feature are not backfilled and are **not durable** on Render Free's ephemeral SQLite.
- **Not real-time provider reconciliation.** The consistency report checks the current **local** demo database. It does not call PayPal and cannot prove that real or sandbox funds moved outside the verified integration test.
- Automated Python tests cover authentication, privacy, atomic event histories, duplicate webhook/capture behavior, seeded-record limitations, corruption detection, and lack of side effects.

## Private RSVP and organizer communications

- The protected organizer workspace now shows each fictional participant's **Going / Maybe / Can't attend / Awaiting response** RSVP and aggregate counts.
- Private invitees can update attendance through their **existing seven-day bearer link** using `POST /api/participant/rsvp`. This new method is the only additional public API action; the link still cannot access organizer data, Gemini, or PayPal.
- A decline made before checkout revokes any outstanding demo contribution approval for that person. The server prevents new organizer approvals, simulations and PayPal sandbox order creation for participants marked declined.
- **RSVP is not a financial transaction.** Changing attendance never silently changes the budget, reallocates an existing share, cancels a previously created PayPal order, or issues a refund. The organizer must review adjustments.
- **Event updates & reminders** creates editable drafts for group announcements, RSVP reminders and preparation updates. Drafts contain only aggregate counts—not individual participant names, private invitation tokens, or secret account links. Messages are copied manually; CircleSplit does not send email, SMS, or chat messages.
- Automated tests cover invite token expiry and revocation, RSVP authorization, disabled checkout for declined attendees, financial immutability, and drafts' explicit sandbox-only language.
- This remains a controlled hackathon prototype with shared organizer credentials and ephemeral SQLite storage; it is **not** a production attendance or consent identity system.

## AI-assisted event preparation (Gemini)

- The protected **AI assistant** now offers a second workflow: **Generate preparation tasks**. Gemini uses the selected fictional event's name, date, description, existing checklist titles, and optionally the organizer's additional context to suggest an actionable plan.
- The AI returns up to **eight new checklist tasks**, a short rationale and a checklist-version signature. Its result is a **preview only**: no event task, payment, budget, approval, invitation, booking or participant detail is changed automatically.
- Organizers can **deselect and edit** any suggestion. Only clicking **Add selected tasks to checklist** calls the separate bulk task endpoint.
- The task submission is **atomic**, deduplicates names case-insensitively, enforces the 40-task cap, and checks a SHA-256 version signature of the currently stored checklist. If a checklist changed since generation, the server rejects the stale proposal with HTTP 409.
- Provider errors share the existing sanitized Gemini adapter and never expose API secrets or upstream responses. The public homepage remains a **browser-local simulation**, and AI endpoints are protected by the existing workspace authentication.
- AI-planned preparation is available even after a PayPal sandbox order exists, because tasks are operational and **do not recalculate shares, invalidate approvals or affect captures**.
- Provider/API calls consume your Gemini quota; no automatic background call is made. This remains a fictional sandbox prototype, and tasks like “confirm venue” must not be mistaken for bookings the AI completed.

## Operations Pulse: action-oriented event health

- New **Operations pulse** section in the protected organizer workspace organizes action priorities around missing people/budgets, allocation discrepancies, unapproved contributions, unfinished preparation tasks, and PayPal SANDBOX orders without recorded captures.
- Open each alert directly in its relevant Events, Contributions, Activity, or Insights tab; filter and search the action queue.
- Event health shows progress on checklists and verified sandbox captures separately. "Planning progressing" is never represented as a successful charge or complete payment.
- **Copy event brief** creates a plaintext summary with no participant names or payment token identifiers and explicitly states that test amounts are not real invoices or debts.
- The transaction feed now returns `event_id` for precise order-to-event association; event names are not unique identifiers.
- `static/pulse.js` is a pure tested module. Node tests cover prioritization, malformed dates, allocation mismatches and avoiding double-counting simulated payments.

## Event Operations checklist and calendar export

- Protected Events page now supports per-event preparation tasks, a completion bar, and a five-task starter checklist.
- Tasks can be updated after checkout begins without altering budgets, participant approval, or payment records.
- Duplicating an event copies checklist titles but resets all completed flags.
- Calendar (.ics) exports are all-day events, produced entirely in the browser with strict date validation, special-character escaping, and UTF-8 line folding.
- Backend and Node tests cover access control, cross-event isolation, idempotence, payment invariants, calendar escaping, and date boundaries. Like all demo records, event tasks may reset on Render Free redeployment.

## Private, revocable participant approval links (hackathon demo)

- Organizers can select **Invite** next to an unpaid participant. The server creates a cryptographically random bearer token and stores **only its SHA-256 hash** in SQLite.
- The invitation uses the URL **fragment** `/participant#token=...` rather than sending the token in a request path/query. The standalone portal clears the fragment and remembers the token for that browser tab's session; no external scripts or third-party requests are loaded.
- The portal exposes only the specific participant's event name/date, own share, approval and sandbox/simulation status. It cannot access the organizer dashboard or call Gemini or PayPal APIs.
- Invitation links expire after 7 days, are revocable, and each regeneration invalidates all previous links. Budget reallocations revoke issued links and reset approvals; a token is bound to its original exact-cent amount.
- **Consent limitation:** Possession of a private link is not proof of legal identity. Organizer "Approve" is explicitly labelled a **demo approval**, distinct from an approval submitted through a participant link. No real payment happens when a share is approved.
- These links and approvals use Render Free's ephemeral SQLite and will disappear after redeployment. The feature is a sandbox-only experience, not a full production user account system.
- Tests verify minimal data disclosure, method-level access, revocation, expiry, budget invalidation, and that bearer links cannot access PayPal or the organizer's records.

## Batch participant import

- The protected Events page supports one-name-per-line participant imports, with optional attendance weight (1–10), for larger fictional groups.
- A single `POST /api/events/{id}/people/bulk` request validates the entire batch, rejects case-insensitive duplicate names against the batch and existing event participants, caps groups at 200, and inserts everyone atomically before recalculating exact-cent shares.
- If an event has a payment order or simulated contribution, the existing budget lock blocks imports. Automated tests cover atomicity, duplicate handling, weighted splits and locks.

## Scenario Lab and reusable event templates

- **Scenario Lab** in the protected workspace previews budget adjustments, additional fictional attendees, and equal versus attendance-weighted splitting. The server uses the same exact-cent largest-remainder allocation as real event budgets.
- Hypothetical changes show per-person before/after shares but **never change approved amounts, payment records, or PayPal orders**. Input is bounded and invalid or excessive scenarios are rejected.
- **Duplicate as new event** copies an existing event's expense lines, attendance weights and fictional participant names as a new reusable template, even if the original event has payment history. It resets all approvals and paid statuses and intentionally does not copy payment objects.
- Backend pytest covers mathematical invariants, preview immutability, secured routes, invalid input and cloning paid events.

## New Insight Center and safer AI review

- Protected workspace **Insights & exports** provides live fictional group funding KPIs, outstanding shares, exact-cent allocation validation, and per-event PayPal sandbox progress.
- Export selected-event participant shares or all event funding totals as CSV. Spreadsheet cells beginning with formula operators are escaped to prevent formula injection.
- Export an explicitly **read-only JSON snapshot** of the current fictional demo events and sandbox ledger (not a database restore or guaranteed backup). Sensitive PayPal order and capture identifiers are excluded. Records on Render Free can disappear after redeploy.
- Gemini proposals are bound to the selected event; switching events invalidates the proposal. Suggestions are only shown as saved **after the server confirms** the bulk expense update. Failed updates retain the proposal for correction and retry.
- PayPal cancellations now direct the organizer to Activity and the existing-order recovery flow instead of creating a new order.
- Frontend analytics and CSV safety checks run in GitHub Actions using Node's built-in test runner.

## Judging access and walkthrough

- Public no-login guest demo: https://circlesplit-ai-demo.onrender.com/ — interactive **browser-local simulation** only.
- Public judge walkthrough: https://circlesplit-ai-demo.onrender.com/judge — clear step-by-step Gemini and PayPal sandbox testing route.
- Protected live integration workspace: https://circlesplit-ai-demo.onrender.com/workspace — this calls real Gemini and PayPal **sandbox** APIs and is protected by HTTP Basic auth.
- [Judge handoff document](docs/JUDGE_HANDOFF.md) and [2:45 video script](docs/VIDEO_DEMO_SCRIPT.md) document the exact evaluation steps without exposing credentials.
- Optional separate judge account uses JUDGE_USERNAME and JUDGE_PASSWORD (18+ characters), enabled with JUDGE_ACCESS_ENABLED=1 and auto-expiring through JUDGE_ACCESS_EXPIRES_AT. Owner credentials remain independent. **Set passwords in Render only; never commit them to GitHub.**
- The protected /api/judge-readiness endpoint shows only whether provider credentials are present and how many captures/webhooks are recorded in the **current ephemeral database**. This does not assert live availability or persist evidence across redeployments.
- Devpost's testing-instructions field must include the separate judge login, not the repository or publicly visible project description. Check the visibility of that field before posting credentials. Never disclose PayPal live buyer or API secrets.
- The separate judge login **does not create isolated per-judge data**: testers should only use fictional event and participant names. This is a controlled sandbox proof of concept, not production authentication.

## Verified provider smoke test (November 2–3, 2026)

The deployed, password-protected organizer workspace completed the following **sandbox-only** test journey:

- **Gemini**: a real HTTP 200 from `/api/ai/parse` returned three editable expense items (court $180, equipment $25, refreshments $30) and a narrative rationale. Human approval is required to add them to a budget.
- **PayPal**: an $11.00 USD fictional participant contribution produced a sandbox Orders v2 order, a buyer approval return to `/workspace?payment=return`, a successful HTTP 200 capture, and HTTP 200 verified-webhook deliveries. The ledger displayed `VERIFIED CAPTURE` rather than `ORDER CREATED` or `SIMULATED`.

The tests verify one specific happy path and do not establish production readiness, universal reliability, or real-money processing. Do not publish sandbox buyer credentials, secret API values, or the shared judge-workspace password in the repository or video.

**Judge walkthrough:**

1. Open the no-login public site and demonstrate event creation and deterministic split allocation using fictional data.
2. Open `/workspace` with credentials provided *privately* in the Devpost testing-instructions field.
3. In AI assistant, submit `Court rental $180, equipment $25, refreshments $30 for twenty people`; review the structured output and only apply to an editable test event.
4. Create a fresh $11.00 test contribution in a new fictional event, approve it, and select PayPal test; approve in the PayPal sandbox buyer account (no real payment methods).
5. If the redirect does not complete, use Activity → Check PayPal to resume the **existing** order. Verify that Activity shows `VERIFIED CAPTURE` and the Overview confirmed sandbox total increases.
6. Check the PayPal sandbox app's webhook logs separately. Never treat a created order or webhook simulator as evidence of a captured payment.

**Important**: Free Render SQLite storage is ephemeral; previous captures and events can vanish on a deploy or restart. The deployed example is not intended for real users. The public guest page never invokes real PayPal/Gemini APIs.

## Public website and protected organizer workspace

- **Public website:** https://circlesplit-ai-demo.onrender.com/ — no login, interactive fictional events and exact-cent splits, entirely **browser-local** (localStorage). Simulated contributions never contact PayPal; the public AI panel is informational and does not contact Gemini. No public action changes the organizer SQLite database.
- **Protected organizer workspace:** https://circlesplit-ai-demo.onrender.com/workspace — HTTP Basic authentication, with credentials stored securely as Render environment variables. Only this workspace may call the real organizer/AI/PayPal APIs.
- **Checkout return:** PayPal sandbox returns to /workspace?payment=return for authenticated capture. Public homepage is *not* a checkout return handler.
- **API isolation:** hosted service enforces Basic authentication on /api/state, /api/transactions, /api/ai/parse, /api/events/*, /api/paypal/orders/* and /api/paypal/capture. The public homepage and /health are openly accessible; PayPal webhook remains accessible for cryptographically verified event delivery.

This arrangement provides anyone a useful no-login demonstration **without exposing a shared mutable backend or triggering third-party API spend**. It is not a publicly available live AI/payment product. For the hackathon, judges can use the guest preview and receive separate controlled credentials to test verified integrations.

## Optional hosted judge demo (Render Blueprint)

The repository includes [render.yaml](render.yaml) for a **Free plan** web service, and the website is already deployed to Render. GitHub main changes trigger automatic deployment.

When CIRCLESPLIT_HOSTED=1, the organizer workspace and all organizer API routes require HTTP Basic credentials and the application **fails closed** until DEMO_PASSWORD is set to a strong value (12+ characters). Configure it through Render's secret environment variables and give judges the username/password privately through Devpost testing instructions. Health checks and PayPal webhook calls are excluded from Basic authentication; webhook calls still require PayPal signature verification.

The Free instance uses **ephemeral SQLite storage**, so demo records may reset during restarts or redeploys. This is suitable only for fictional hackathon demo data, not real users. For a PayPal sandbox redirect you must set PUBLIC_BASE_URL to your deployed **HTTPS** URL, and create a Sandbox webhook in the PayPal Developer Dashboard. Set credentials only in the Render environment, never in source.

The shared judge password is **not** participant identity: it protects the organizer demo from anonymous visitors but does not establish individual payment authorization. Before any real users or money, replace it with proper accounts, participant approvals tied to identities, audit controls and production data storage.

## Safety and demo limitations

The MVP uses a single locally trusted organizer and **does not yet implement accounts or role-based permissions**. It should run locally (127.0.0.1) and must not be exposed directly to the Internet. AI output is untrusted and cannot initiate payments. Do not claim integration success until you test real sandbox credentials. PayPal orders remain authorization- and identity-sensitive. The project does not act as an escrow, money transmitter, or real payment splitting platform.

## Submission requirements

Official hackathon: https://paypalaihackathon.devpost.com/
Deadline: **November 12, 2026 at 12:00 PM PST**.
The judges require a working demo, public source code under an approved open-source license, documented PayPal + AI integration, and a public YouTube demo **under 3 minutes**. This repo is a work in progress and has not yet met every requirement.

## License

MIT. See [LICENSE](LICENSE).
