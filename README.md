# CircleSplit AI

AI-assisted group budgeting with participant approval and PayPal Sandbox checkout.

> **Hackathon development build. No real money movement.** This project is not production-ready and must not be publicly deployed without authentication, rate limits, and credential review.

**Devpost draft:** https://devpost.com/software/circlesplit-ai

## What it does
- Organizer creates an event, records expenses and participants.
- Deterministic integer-cent allocation makes equal or weighted shares add up to the exact event total.
- Participants explicitly approve their shares.
- A private invitation holder may withdraw approval before checkout; an organizer cannot demo-approve that share again until the holder approves via private link. This is fictional capability-based consent, not identity verification.
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

## Safe preflight for new PayPal Sandbox checkout

In the protected organizer **Contributions** tab, **Check readiness**
performs a read-only `GET /api/paypal/checkout-readiness/{event_id}/{person_id}`
and shows why a fictional participant is or is not eligible for a **new**
PayPal Sandbox order: approval/withdrawal, declined RSVP, unpaid positive
share, existing or uncertain prior order, full-event exact-cent allocation,
configuration, and the optional verified-durable-storage requirement. This
endpoint does not contact PayPal, create an order, move money or mutate the
ledger. A green result is a *local readiness signal*, not a PayPal provider
status check or guarantee that checkout will succeed.

**PayPal test** now runs that preflight, requires explicit confirmation
including the exact USD amount, and redirects only to an HTTPS
`sandbox.paypal.com` hostname after order creation. The server independently
**repeats local checks in the same SQLite transaction that inserts the new
order**, including verifying every participant's exact allocation against the
current event expenses. If local data is inconsistent, the server returns 409
before allocating any payment row or making a PayPal request, regardless of
what an earlier read-only preflight said.

Once an order may exist, a timeout, lost response, or unexpected redirect
must **never** trigger another checkout. Use **Activity → Safe payment
recovery** and compare against the provider's sandbox records. All PayPal
traffic remains sandbox only; this does not address ephemeral storage or
external payment verification.

## Guided, sandbox-safe evaluation for hackathon judges

The public [judge walkthrough](https://circlesplit-ai-demo.onrender.com/judge)
now includes a five-stage, interactive checklist: public browser simulation,
Gemini proposal, private-link share consent, optional PayPal Sandbox capture,
and engineering evidence. Review progress stays in memory in the judge's
current page; marking a step is **not** a test result or a submission.

The walkthrough includes reproducible test expectations ($10/3 exact-cent
allocation and $180 + $25 + $30 Gemini extraction), an optional browser
clipboard action for the fictional AI prompt, and a public **source-only**
GET `/health` check. The latter reports a deployed revision if available,
but is **not** proof of login, PayPal capture, AI availability, or persistent
storage. No PayPal/Gemini requests, payments, invitation tokens, or financial
mutations occur on the public guide. Credentials belong solely in private
Devpost testing instructions.



A private invitation now explains **how the fictional contribution was
calculated** before the participant approves it. The participant portal shows
the total estimated event budget, the number of people sharing it, the
equal/weighted split method, and cost-category subtotals. The view returns
**no other participant names, individual shares, contact details or PayPal
identifiers**. Amounts are integer USD cents, using the same largest-remainder
allocator as the organizer.

The server recomputes the full allocation before accepting private-link
approval. A local inconsistency (for example, allocated shares not matching
the category/budget totals) blocks approval, even from older API clients.
The browser sends both **the displayed share and displayed total** as an
optimistic quote check. If either has changed, the server returns HTTP 409
and the participant must refresh and review before approving. Existing
legacy API clients with no quote body remain supported, but they are still
subject to the independent allocation-integrity check and invitation
invalidation when budget changes.

These are **estimates, not invoices or charges**. Approving this private-link
quote does not verify the participant's real identity or call PayPal. The
organizer still controls actual Sandbox order creation separately.

## Compare two private reconciliation snapshots without uploading them

In the protected **Activity → Compare private recovery snapshots** panel,
select an earlier and later `paypal-sandbox-reconciliation-manifest` JSON file.
Both files remain on the device: JavaScript reads them through the file input,
checks their server-exported SHA-256 digests with the browser's Web Crypto API,
and compares the records **without any API upload, database write, or PayPal
request**. Only bounded aggregate counts and warnings appear in the interface;
no participant names or provider IDs are displayed in the comparison results.

When the database incarnation is unchanged, the comparator matches records
using local payment IDs. When it changes, local IDs can be reused and are
**never** used to establish continuity: only known matching PayPal Sandbox
order IDs are comparable. Earlier attempts lacking a provider order ID are
reported as untrackable across the reset. Reports include missing/new references,
status progression, completed-status regressions, capture-ID conflicts,
amount changes, and, when safe, local linkage changes.

The tool rejects malformed manifests, duplicate IDs, mismatched SHA-256
digests, reversed snapshot times, and oversized files (over 8 MB each). It
clears selected file references after each attempt. The comparison is strictly
**investigative**: SHA-256 without a trusted signature is not proof of origin,
an absent record does not mean PayPal never processed it, and a locally
completed payment is not proof of external settlement. **Never retry a
possibly existing charge based on this report.**

## Read-only global PayPal Sandbox ledger integrity audit

The private organizer **Activity → Local payment integrity audit** panel checks
the entire current SQLite payment ledger on demand via
`GET /api/paypal/ledger-audit`. It reports full-database counts and up to 100
representative findings by local numeric record identifiers, with no
participant names, bearer links or provider credentials in the response.

It checks for missing events/participants, cross-event payment references,
zero/invalid or mismatched contribution amounts, completed rows without
capture IDs, capture IDs on incomplete rows, mismatched participant paid
statuses, repeated PayPal orders for one participant, and simulated statuses
that coexist with PayPal orders. **Unresolved checkouts alone are not treated
as integrity violations**; they are counted separately and belong in the
existing safe recovery queue. This audit makes no provider request and never
mutates the database.

A locally consistent result does **not** prove external PayPal settlement,
capture existence upstream, identity, data durability or reconciliation
completeness after an ephemeral storage reset. See the security notes.

## Private PayPal Sandbox reconciliation manifest (manual download)

The organizer-authenticated **Activity → Save private reconciliation manifest** control
downloads one JSON snapshot from `GET /api/paypal/reconciliation-export`. It
includes **every current local payment attempt** (up to 10,000 records), its
fictional event/participant mapping, exact USD cents, local status, creation
timestamp, PayPal Sandbox order ID (if known) and capture ID (if recorded).
It also records the database incarnation ID and a SHA-256 digest of the
canonical record array to help identify accidental changes after download.

The manifest contains **private participant names and payment-provider
identifiers**. Store it securely on a trusted device. It deliberately excludes
secret request/capture idempotency keys, bearer invitation tokens, credentials
and webhook payloads. It is **not importable** into CircleSplit, and the
planning-only restore endpoint rejects it. It is **not** a PayPal receipt,
proof of settlement, durable database backup or cryptographically signed
audit. A digest is not a signature. It can only help manually compare local
records with PayPal Sandbox after a reset; missing records cannot be recovered
from an earlier-lost database. For larger ledgers the export fails with
HTTP 413 rather than silently truncating a financial snapshot.

See [security boundaries](docs/SECURITY.md) and [storage recovery guidance](docs/PERSISTENT_STORAGE.md).

## Safe payment recovery across large demo ledgers

The protected **Activity → Safe payment recovery** view prioritizes unresolved
sandbox orders even when they are older than hundreds of completed payments.
The paginated `GET /api/paypal/recovery?limit=50&offset=0` endpoint returns
complete local status totals and an `attention_count` calculated over the
entire SQLite payment table. It includes orphaned/inconsistent payment records
for manual review and exposes only existing known order IDs for safe status
checks. Creating/capturing a new charge is **never** performed by this view.

Pagination uses a bounded offset; changes between page requests can shift
rows, so refresh from page one after reconciliation. This is local data only,
not external provider settlement proof. See [security and recovery
limitations](docs/SECURITY.md) before using it for a judging demo.

## Storage safety and reset detection

The protected workspace now reports a database incarnation ID, persistent-mount
status and a warning when hosted SQLite is on an ephemeral filesystem. A changed
incarnation ID signals that the local DB was replaced and existing PayPal
**Sandbox** orders may need independent reconciliation.

The optional `CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB=1` gate blocks **new**
sandbox checkout when the SQLite file is not under a verified filesystem
mount. Existing recovery, capture and signed webhook operations stay enabled.
It is off by default so the current Free judge demo is unaffected. An
[optional paid persistent-disk example](render.persistent.example.yaml) is
provided but **not applied**; read [storage migration and safety notes](docs/PERSISTENT_STORAGE.md)
before making any hosting or billing changes. A persistent disk is not an
external backup or a production-ready financial database.

## Confirm that Render runs the latest code

The public `/health` endpoint includes `git_commit`: a validated, 40-character
Git SHA automatically supplied by Render. Compare it against the latest GitHub
`main` commit to confirm which source revision is running at
https://circlesplit-ai-demo.onrender.com/health. If it is `null` or differs,
the current deployment is **not verified**. Health responses are not cached.

See [Deployment verification](docs/DEPLOYMENT_VERIFICATION.md) for steps and
limitations. This check cannot prove PayPal/Gemini availability or storage durability.

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

## Download the event agenda as a calendar (.ics)

- The protected **Events → Event run of show** section now has **Download calendar (.ics)** when the current event has at least one agenda item. Participants with an active invitation link see their own **Download calendar (.ics)** button in the private portal. Empty agendas return HTTP 409 instead of generating an empty or misleading calendar.
- Two routes are available: organizer-authenticated \`GET /api/events/{eid}/calendar.ics\` and private bearer-invitation \`GET /api/participant/calendar.ics\`. The participant route requires the existing valid, unrevoked and unexpired capability link; it never uses invitation tokens in download URLs, redirects, or the file itself.
- Downloads contain only event name, agenda titles, participant-visible agenda notes, event date and activity times. There are **no participants, addresses, budget amounts, approvals, PayPal identifiers, invitation URLs or private bearer tokens** embedded in the file. The output is a local calendar file, not an outgoing email or calendar invitation.
- All events have **floating local wall-clock times**, because CircleSplit currently stores no verified location/timezone. The \`.ics\` entries omit both TZID and UTC suffixes; the organizer and attendees must confirm the event timezone before importing. Apps may interpret floating times using the importing user's timezone; this is unsuitable for cross-timezone travel without manual checking.
- Each activity has a deterministic, opaque UID derived from event and slot identifiers, a \`SEQUENCE\` matching the agenda revision, a UTC DTSTAMP tied to the persisted agenda revision timestamp (stable across repeat downloads), and RFC 5545-compatible text escaping, UTF-8 octet-aware line folding and CRLF termination. This helps calendar clients recognize updates when a new version is **manually downloaded and reimported**, though client behavior varies.
- The server sets \`Cache-Control: private, no-store\`, attachment disposition and no-sniff headers, and validates actual calendar dates and same-day non-overlapping slots. Export is read-only; no RSVP, schedule acknowledgement, payment, or approval is changed.
- The calendar is marked **tentative** and clearly states that it is not an actual reservation, charge, invoice or confirmed booking. It does not automatically sync, send calendar updates, book venues or create real payments.
- Backend and serialization tests cover owner-vs-bearer separation, revoked links, event isolation, exact event times, escaping of malicious calendar-property content, multibyte Unicode line folding, stable UIDs after edits, sequence increments and complete financial state isolation.

## Agenda change acknowledgements — review tracking, not financial consent

- **Private participant portal**: a participant who holds a valid, unexpired invitation link can see the latest event schedule revision and explicitly press **I've reviewed this schedule**. The private page shows whether the current revision was acknowledged, without exposing any other participant's name, RSVP, contribution, or review status.
- **Organizer Events page**: the Run of Show section displays the current agenda version, how many participants have acknowledged it, how many are pending, and an expandable per-person review status list. This uses the same fictional participant records as the rest of the protected workspace and does not constitute real-world identity proof.
- Creating, changing or deleting an agenda slot **increments the agenda revision**. A no-op edit does not. An acknowledgement is valid **only for that exact current revision**; a stale browser returns HTTP 409 and must refresh/review before retrying. Duplicate acknowledgements are idempotent and create no duplicate history entries.
- A meaningful change to event name/date/description also advances the agenda revision if a schedule has been published, preventing a newly issued invitation from treating the old schedule as acknowledged.
- A new **POST /api/participant/agenda/ack** endpoint accepts \`{"expected_revision":1}\` and requires the existing bearer invitation. It is scoped to that invitation's participant and event; it cannot change RSVPs, consent, simulated contributions, PayPal sandbox records, or any other participant's acknowledgement. It does not automatically notify people about edits.
- **Database migration** adds an agenda revision/timestamp to events and acknowledged revision/timestamp to participants. Pre-existing events with an agenda start at revision 1, not already acknowledged. Cloning and planning-only restoring a schedule starts at revision 1 with zero acknowledgements; no old acknowledgements or private invitation tokens are copied.
- This is a private-link **self-reported review**, not proof that an identified person read the details. Timezone handling remains event-local and unspecified, so the organizer should communicate the location and timezone clearly. All new data remains on Render Free's temporary SQLite until durable hosting is implemented.

## Event run of show & private participant agenda

- The protected **Events → Event run of show** card supports up to **20 activities per event**, with 24-hour start/end times, a short title, and optional participant-visible details. Organizers can add, edit or remove slots. The interface and backend reject invalid times, overnight entries and overlapping activities. Adjacent slots are permitted.
- Times are **event-location wall-clock time**, not dynamically converted across timezones; the organizer is responsible for making the event location/timezone clear to attendees. This is a single-day agenda tied to the event date, not an actual booking or notification.
- Participants with a **valid, unexpired, nonrevoked private invitation link** see only the event agenda, their own share and their own RSVP/approval status. The private page has a manual **Refresh** button. No other participants' identities, shares, organizer tasks or payments are returned.
- Agenda details are intended to be shared with all invitees. Organizers must not enter secrets or sensitive participant information. The participant page uses safe text rendering for all organizer-entered content.
- **Financial separation:** changing an agenda item never recalculates a budget, alters a payment or clears approval/RSVP responses. Logistics can change after sandbox checkout starts, but **the organizer must manually inform participants**. The system does not send emails, SMS, push alerts or amended calendar invitations.
- Agenda entries are recorded in privacy-limited event history without storing their free-text contents. Event duplication copies the agenda to the new unpaid plan.
- Planning backup v1 remains backwards compatible: old JSON files without an \`agenda\` field still restore; new exported backups include validated agenda items and restore them to fresh events. Agenda items contain no invitation or payment history.
- Python and Node tests cover validation, strict access separation, same-event scoping, overlap handling, exact-cent/payment invariants, invitation-only visibility, backup compatibility and cloning.
- As elsewhere, the database is temporary on Render Free. The new feature is a sandbox prototype, not a production calendar or messaging service.

## Guarded event detail editing and stale-change protection

- The protected **Events** page now provides **Edit event details** for the current event's name, calendar date and description. The editor preserves typed values on server errors and asks for confirmation before meaningful changes.
- New authenticated `PUT /api/events/{eid}/details` uses a required **expected name/date/description snapshot**. If event details changed after the form was opened, the server rejects the stale write with HTTP 409; the user must refresh and review the current details.
- A meaningful change to event identity or schedule **invalidates prior participant consent**: RSVP responses reset to `pending`, demo approvals clear, and existing private invite tokens are revoked. Event budgets, participant IDs, assigned exact-cent shares, prepared tasks and payment records are **not** modified.
- Editing is blocked if a PayPal sandbox order has been initiated or a simulated contribution recorded. A truly unchanged edit is a no-op and leaves prior consent and invitations intact.
- The server validates real ISO calendar dates, trimmed names and 180-character descriptions, rejects extra fields, and writes the event update, consent resets and privacy-safe history entry in **one SQLite transaction**.
- This is not a real-time notification system. Following a schedule change, the organizer must **issue new invitation links and communicate the new details manually**. External calendar invitations and previously sent messages are not automatically updated.
- Tests cover invalid date rejection, old-token invalidation, RSVP/approval reset, exact-cent share isolation, no-op preservation, stale-browser conflicts, payment locks and organizer-only authorization.

## Guarded financial editing of expenses and participants

- In protected **Events**, existing expenses now have **Edit** controls for their title, exact-cent USD amount and category. Participants have **Edit** controls for names and attendance weights (1–10). Editors are clearly labeled and allow cancellation.
- A changed expense or participant is saved **atomically** via organizer-only `PUT /api/events/{eid}/expenses/{expense_id}` and `PUT /api/events/{eid}/people/{pid}` endpoints. All shares are recalculated by the server's exact-cent allocation. Existing approvals are reset and private invitation links revoked, because their consented amount/details might no longer be valid.
- Neither financial editing endpoint can change records once a simulation is recorded or any PayPal sandbox order has begun. Such attempts return HTTP 409 without mutating the event. Editing the category alone uses the existing separate metadata-only endpoint; it does **not** reset approvals before the payment lock.
- Submitting identical details is a **no-op**: no history entry, approval reset, or invitation revocation. Changed edits get a history entry with IDs, amounts or weight metadata, **not participant names or invitation tokens**.
- The UI asks for explicit confirmation before a meaningful save and keeps the edit form intact when the server rejects a request. Server-side Pydantic validation checks names, weights, categories, expense amounts and participant-name collisions.
- Regression tests verify recalculation, approval revocation, expired links, no-op preservation, payment locks, validation, organizer authorization and unchanged financial state on failure. The feature remains a fictional sandbox prototype on temporary SQLite storage.

## Quick Start — event templates (fictional sandbox planning)

- The protected **Events** page includes a **Quick Start** wizard with five ready-made examples: **Volleyball night, Group dinner, Weekend getaway, Study meetup, and Community cleanup**. The user can preview the cost breakdown and checklist before creating a new plan.
- The organizer can edit the new event name/date and include or exclude **example expense estimates** and **preparation tasks**. All templates are explicitly hypothetical: no actual prices, venue reservations, participants, approval records, PayPal orders, invitation tokens, or real-money transactions are created.
- New authenticated `GET /api/event-templates` returns the fixed catalog, plus a `POST /api/event-templates/{key}/create` endpoint to atomically create an event, category-tagged expense estimates and an unchecked preparation checklist.
- Server validation includes strict JSON fields, actual calendar dates, trimmed names, a known template ID, a valid UUID request key, and bounded fixed expense categories/amounts.
- Template creation is **idempotent** within the current database. The request key and SHA-256 hash of its creation settings are stored transactionally in `template_creations`; retrying the same request returns the existing event instead of creating a duplicate. Reusing a key for different details returns HTTP 409. Keys are not financial transaction identifiers.
- Organizer event history receives an `event_template_created` entry with only the template ID and counts. A failed multi-record write rolls back completely.
- This is designed to reduce onboarding friction and help demonstrate CircleSplit's planning workflow. **Existing event plans, approvals and sandbox payments remain unchanged**.
- Like other local SQLite records, templates and idempotency records reset after a Render Free database reset. Never treat estimated costs as actual charges, invoices, reservation confirmations, or amounts owed.

## Planning backup & safe restore (manual, private, non-financial)

- The protected organizer workspace now includes **Backup & restore**. The owner can explicitly download a versioned `planning-backup` JSON and inspect a selected backup file locally before any restore is requested.
- Backups contain **event names, dates, descriptions, equal/weighted strategy, planned expense titles/categories and integer cents, participant names and weights, preparation task titles, and advisory spending ceilings/contingency preferences**. Because participant names are included, treat these JSON files as private; CircleSplit does not automatically email or upload them to external storage.
- The backup **never includes participant IDs, existing share amounts, approvals, RSVP answers, payment statuses, PayPal orders/captures, webhook identifiers, invitation URLs or bearer secrets, or historical activity**. The older **read-only sandbox demonstration snapshot** under Insights remains separate and **cannot** be imported.
- Restoring is an **explicit, confirmed** action. Every event is created **as a brand-new unpaid plan with fresh IDs**. Splits are recomputed with exact cents. All restored participants begin unpaid/unapproved with pending RSVP; task completion resets to unchecked; no invitation or payment is created.
- The server validates a strict versioned schema (`schema_version: 1`, USD), forbids unexpected nested fields, checks real calendar dates, participant/task uniqueness, weights, categories, amounts, and limits of 25 events / 700 KB / bounded combined record totals. Invalid multi-event requests are rejected **before writes** and all inserts share a single SQLite transaction.
- **Double-submit safety:** the server hashes normalized planning content and records the fingerprint in `planning_restores` in the same transaction. Re-importing identical planning contents into the current database returns HTTP 409 without creating duplicate events. This protection resets if the ephemeral database itself is erased.
- **API:** authenticated `GET /api/planning-backup` (download) and `POST /api/planning-backup/restore` (validated import), both inaccessible to public visitors and participant-link holders.
- **Important:** This mitigates *planning data loss only if the owner regularly downloads and securely retains the file*. It does not provide continuous backups, preserve payment history, restore approvals or guarantee recovery of PayPal activity. Durable database storage and individual authentication are still required before production use.

## Payment recovery and capture retry safety

- The protected **Activity → Safe payment recovery** panel now shows current local PayPal sandbox order states: **creating** (order creation response missing), **created** (existing order can be checked), **capturing** (one capture attempt already made), and **completed** (capture identifier recorded).
- The new **GET /api/paypal/recovery** endpoint is read-only and organizer-authenticated. It returns the latest 200 local records, a visible truncation warning, safe next-action guidance, and existing PayPal order IDs only for orders with an established ID that can be checked. It does not issue API calls to PayPal or initiate payments.
- **Capture concurrency guard:** before requesting a sandbox capture, CircleSplit atomically marks the payment **capturing**. Any repeated capture call while that request is in flight—or after its outcome becomes uncertain—fails with HTTP 409. This avoids a second capture request from a browser refresh, duplicate click or network timeout.
- A failed/timed-out capture remains locked. The organizer can use **Check existing PayPal order**, which queries PayPal's existing order details and validates intent, event/participant reference, currency, amount and captured transaction before updating local records. If PayPal reports **APPROVED** after capture was already attempted, CircleSplit intentionally **does not offer a second capture**.
- An ambiguous **creating** state with no returned order ID requires *manual PayPal sandbox account review*; CircleSplit does not automatically retry order creation because doing so could create a duplicate order.
- Completed local payment records with **no capture ID** now fail closed instead of reporting a verified capture. Successful capture history remains idempotent if a webhook or reconciliation completes while a previous capture request is returning.
- **Provider URL validation:** the PayPal API adapter now accepts checkout redirects only to the explicitly trusted \`www.sandbox.paypal.com\` or \`sandbox.paypal.com\` hosts over HTTPS; other URLs are rejected without sending the browser to the untrusted domain.
- The manual participant form now preserves user input when the server rejects a save, matching existing expense-form behavior.
- Tests cover ambiguous order creation, capture timeout, no duplicate capture requests, safe reconciliation of an already attempted capture, malformed local completion, authorization, and forged PayPal redirects. This feature remains sandbox-only, with temporary SQLite; it is *not* an assurance of durable recovery after a Render restart.

## Protected closeout preview (read-only and sandbox-only)

- New **Closeout preview** workspace tab shows an organizer's **read-only** event closing summary. It uses a protected backend \`GET /api/events/{eid}/closeout\` endpoint and does not mutate the database, create transactions, close an event, create invoices, contact PayPal or send messages.
- Report totals distinguish **verified PayPal sandbox capture records** from **simulated contributions** and **amounts unverified against the PayPal sandbox**. Unverified amounts are never described as money owed or debts. Payment orders that have not been captured are listed separately.
- Per-person reconciliation displays assigned share, approval source, RSVP response, local status, verified sandbox amount, simulation amount, unverified amount and number of pending orders. This protected view is not accessible through participant invitation tokens.
- Stages include **needs setup**, **needs review**, **pending sandbox orders**, **simulation activity**, **unverified sandbox funding**, and **sandbox captures cover planned budget**. Even the last stage is specifically limited to local PayPal sandbox ledger evidence and is **not real-world settlement**.
- The closeout includes the existing local financial-integrity checks and preparation/approval/attendance counts. A discrepancy overrides a favorable payment stage, preventing a corrupted allocation from being called complete.
- **Copy summary** produces an aggregate-only plaintext report without individual participant names. **Download CSV** produces a clearly labeled fictional sandbox report with participant names; keep this file private. Exports omit API keys, PayPal order/capture/webhook identifiers and invitation URLs.
- All previews are temporary and not a restorable backup. Render Free's ephemeral SQLite can erase data after deployment; no historical statement should be treated as permanent. This feature does **not** include real payment finalization, provider reconciliation, refunds or payout logic.
- New backend and JavaScript tests cover sandbox-only stage calculation, pending orders, completed captures, simulations, corruption, authorization and export wording.

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
