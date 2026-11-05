# Security and operational boundaries

This repo is a hackathon **prototype**, not an online payment platform. All user and event data is fictional. All PayPal API traffic goes to the SANDBOX endpoint. No production PayPal payments are supported.

## Trust assumptions

- Local development defaults to a single trusted organizer with no accounts.
- CIRCLESPLIT_HOSTED=1 makes the app require a shared judge password (HTTP Basic auth). Without a 12+ character DEMO_PASSWORD, the hosted app responds with HTTP 503 (fail-closed).
- Shared judge credentials are **not** secure individual participant identities. A separately configured expiring **judge** role can explore the shared fictional organizer workspace but cannot initiate or reconcile PayPal Sandbox payments; the **owner** credential retains those operations.
- The PayPal webhook is exempt from judge Basic auth because PayPal cannot send judge credentials, but its signature must be verified by PayPal before any state change.


## Signed Sandbox webhook outcome audit (November 6, 2026)

The existing public `POST /api/paypal/webhook` still requires valid
PayPal signature verification before any database mutation. A non-object
JSON envelope or invalid webhook event identifier fails locally with
HTTP 400; a failed signature still cannot create payment or audit rows.
Valid signed `PAYMENT.CAPTURE.COMPLETED` events with an unknown local
order, missing order reference, malformed capture resource or mismatched
currency/cents now receive a **non-settlement outcome** recorded in
`webhook_events.outcome`. Other provider event types are counted
separately. Exact matches use the preexisting global capture uniqueness
and payment state settlement guard. A conflicting capture raises HTTP
409 and rolls back the event insertion to allow provider retry/manual
investigation, preserving financial correctness.

The migration introduces a non-null `outcome` column defaulting to
`legacy_unclassified`. Previous signed webhook IDs are preserved and
**not** retrospectively declared paid. The protected read-only
`GET /api/paypal/webhook-audit` returns aggregate outcome counts;
the Activity UI validates those counts and renders only fixed labels
and numbers. Neither API nor UI exposes webhook, capture or order IDs,
credential material, invitation tokens, event metadata or raw
provider payloads.

The audit is local-only. Render Free SQLite loss can erase webhook
observations, and a signed unmatched capture may arrive before local
order creation finishes. The feature does not automatically retry
captures, recreate orders, reconcile PayPal, or restore lost records.
Manual operator comparison with PayPal Sandbox remains required.

## Hosted judge credentials cannot operate PayPal Sandbox (November 5, 2026)

On `CIRCLESPLIT_HOSTED=1`, Basic authentication marks successful
owner credentials as `owner` and optional time-limited judge
credentials as `judge`. Only the owner can invoke non-webhook
`POST /api/paypal/*` actions. That includes initial order creation,
existing-order reconciliation (which may settle a completed capture),
and direct capture. New POST provider actions are denied by default
without enumerating every individual endpoint. The webhook exception
is narrow and remains protected by independent provider signature
verification. Unauthorized attempts return HTTP 403 before a rate-budget
charge, PayPal request, payment-row mutation or settlement.

`GET /api/state` advertises the display-only role and boolean payment
permission to the authenticated browser. `GET /api/paypal/checkout-readiness`
reports an organizer-credential blocker when viewed by the judge.
The judge-facing UI disables/hides provider action controls and private
reconciliation export, but the **middleware is the permission authority**.
Judge sessions can still inspect read-only local payment recovery and
audit summaries, and operate fictional planning/simulation actions.

The private reconciliation manifest retains its existing owner-only
download guard. An expired or disabled judge credential cannot access
the hosted workspace. This is limited role separation for a shared
hackathon database: judges can still mutate fictional event planning,
not true read-only tenancy; there are no real identity-bound users,
individual payment authorization, or production payment capabilities.

## Read-only affordability scenario safety (November 5, 2026)

- The organizer-only `POST /api/events/{eid}/affordability` validates a
  strict positive USD cap (up to $100,000.00), 0–50 additional people and
  an equal/weighted strategy. It enumerates bounded hypothetical attendance
  counts with the real integer-cent allocator. No AI or PayPal calls.
- The endpoint reads only the selected event, its expenses, weights and
  the existence of approvals/previous orders. No attendance, payment
  approval, invoice, order, ledger entry, webhook, or invite is written.
  The pre-existing authenticated hosting boundary and private cache
  policy remain in place.
- The response distinguishes a feasible cap from an impossible result
  within the requested attendee range and explains that additional people
  and payments are fictional assumptions. If checkout was already
  started, it warns that actual budget mutation can be locked.
- The UI validates the expected response, escapes server text, clears
  stale results after an event or assumption change, and never presents
  the hypothetical quote as consent or payment authorization.

## Encrypted backup continuity comparison (November 5, 2026)

- `tools/encrypted_snapshot.py compare` decrypts each archive into a
  separate private temporary directory, authenticates both archives and
  applies the offline read-only ledger-integrity audit before comparison.
- Stored provider order and capture identifiers are compared **only in
  process memory**, never logged, returned, published or sent over the
  network. The output reports aggregate missing/changed counts and
  database epoch prefixes only. Local payment IDs are never matched
  across storage resets.
- A changed incarnation, missing prior known order or capture, amount
  drift, capture conflict, regressed completion, decreased aggregate
  counts or nonchronological archive produces review-required status.
  Historical unknown-order attempts remain fundamentally ambiguous.
- A green comparison is **not** proof of payment settlement or
  successful external backups. Missing records never authorize a new
  PayPal charge; external reconciliation is still mandatory before
  financial recovery. No API route or live payment mutation is added.

## Optional operator-only encrypted backup (November 5, 2026)

- `tools/encrypted_snapshot.py` is **not** imported by the hosted web app.
  Only `requirements-ops.txt` installs the additional audited cryptography
  library. No new web routes or third-party calls are introduced.
- The `seal` command performs a consistent SQLite online backup in a
  private staging directory and encrypts the SQLite file and matching
  manifest together with streaming AES-256-GCM. Header, ciphertext lengths,
  and content are authenticated. Fresh random salt/nonce are required for
  every archive; scrypt derives the encryption key from a private secret.
- `keygen` creates a high-entropy secret file without printing it.
  The secret must be kept physically and logically **separate** from the
  offsite `.csb` archive. File-based secrets are never supplied in
  command arguments, environment variables, JSON reports or Git history.
- Encryption output and secrets are written with no-overwrite semantics.
  On POSIX, private destination directory mode 0700 and secret file
  permissions 0600 are checked. Wrong key, tampering, malformed headers,
  public destination directories and symlink attacks fail closed.
- `verify` and `drill` decrypt only in isolated temporary directories
  and remove plaintext afterwards. The drill checks local ledger semantics;
  it does not move money or restore payment records. Raw SQLite staging
  bytes do transiently exist on disk during encryption/decryption; a
  compromised machine, swap, live process or key loss is not protected.
- This is **not automated offsite backup** and cannot preserve the active
  Render Free database by itself. AES-GCM authentication is not a PayPal
  receipt, individual identity proof, remote storage guarantee or recovery
  sign-off.

## Offline SQLite snapshot controls (November 5, 2026)

- `tools/sqlite_snapshot.py` is **offline operator code only**. It adds no
  HTTP routes, public file serving, payment import or automatic provider
  interaction. `create` uses SQLite's supported backup API while preserving
  committed WAL records; it checkpoints and converts the private staged
  output to a standalone SQLite file before publishing it.
- Private output files use restrictive permissions (POSIX directory 0700,
  files 0600), refuse overwrites and symlink sources, and are ignored by
  Git. Their matching manifest only contains incarnation, aggregates,
  timestamp, checksum and size. The raw SQLite DB still contains sensitive
  bearer-invitation hashes, PayPal Sandbox references and idempotency keys:
  store encrypted offsite, never publicly upload or share.
- `verify` checks SHA-256, size, integrity, expected financial schema and
  aggregate counts. `drill` rehearses reading a copy in an isolated
  temporary directory, then removes it. It additionally applies the
  application's existing bounded local payment-integrity audit to the isolated
  copy. Aggregate `issue_counts`, `unresolved_orders` and review status
  are emitted without exposing payment/participant identifiers. A verified
  database with inconsistent payment links or capture flags produces
  `NEEDS_REVIEW` and CLI exit 3, not a falsely clean pass.
  No command restores or overwrites the live payment database. A checksum
  alone cannot authenticate the snapshot or prove upstream settlement.
- The active Free hosting is still ephemeral; nothing here performs
  background backups or upgrades paid infrastructure. An actual financial
  restore/migration requires controlled downtime, external PayPal Sandbox
  reconciliation and deliberate operator review to avoid double charges.

## Browser-local reset/rollback sentinel (November 5, 2026)

- On initial authorized workspace load, the browser can remember a **short**
  database incarnation prefix, aggregate current-local verified-capture and
  webhook-event counts, and observation date. No participant identifiers,
  PayPal order or capture IDs, invitation tokens, credentials, or raw
  reconciliation manifest contents enter this checkpoint.
- Reopening in the *same browser profile* compares those previous values
  to the protected read-only `/api/judge-readiness` response. A changed
  incarnation or decreased count triggers a workspace-wide warning.
  Unresolved warnings do **not** overwrite the earlier stored checkpoint;
  healthy observations move high-water counts forward.
- Explicit acknowledgement after external manual investigation requires
  confirmation and a *fresh unchanged* server observation. This only
  replaces the local browser checkpoint; it is not proof of PayPal
  settlement or a reconstruction of lost orders. Browser storage can be
  disabled, erased or altered by local users; it is **not trusted**, shared
  across devices, a durable backup, or an automated offsite monitor.
- The feature adds no new payment mutation, external storage, hosted
  secret, third-party request or identity credential. The existing
  Sandbox-only, no-automatic-retry rules still apply.

## Existing Sandbox order reconciliation after delayed provider responses (November 5, 2026)

`POST /api/paypal/order-status/{order_id}` and `POST /api/paypal/capture`
now snapshot the original physical SQLite incarnation and immutable payment
identity before their provider network calls. After each awaited provider
GET or capture, the server rechecks the incarnation, local payment ID,
event ID, person ID, exact cents, original request/capture keys, provider
order ID and creation timestamp **inside its new local transaction**.
Any difference or missing row is a fail-closed HTTP 409 requiring manual
review: the external Sandbox order might have completed already.

This prevents stale PayPal status and capture data from changing a
re-created SQLite row with a reused integer ID (even when a test fixture
reuses the same provider order ID). The status endpoint also rechecks
concurrent local transitions so it never suggests a second capture when
the existing order is already `capturing`. The provider status check
requires an appropriately shaped single purchase unit and validates
optional custom/reference IDs against the saved event/participant.

Provider responses, SQLite snapshots and local capture IDs are not
substitutes for PayPal's external ledger. No automatic capture retries,
forced account reconciliation, or production payments were introduced.

## In-flight Sandbox order binding and stale SQLite resets (November 5, 2026)

`POST /api/paypal/orders/{event_id}/{person_id}` now snapshots the local
SQLite incarnation and inserts the `creating` record, idempotency key,
capture key and exact amount before the network request. After the response,
the server refuses to change any payment row unless the original incarnation,
request keys, event and participant identifiers, amount, prior status and
empty remote ID still match atomically. This prevents a recently reset
ephemeral SQLite database from misassigning a late PayPal Sandbox order to
a different payment with the same reused integer ID. The PayPal adapter and
response handler enforce strict ASCII order IDs and trusted HTTPS Sandbox
checkout URLs without credentials or non-default ports.

A rejected late response does **not** erase the original remote transaction.
The local creating lock remains where its database still exists. If the
database disappeared, manual provider-ledger reconciliation is required;
the system must **never** automatically send a second create/capture
request. This is a narrowly scoped mitigation, **not durable storage**,
identity verification, or guaranteed detection of historical requests lost
after a later restart.

## Provider-verified Sandbox capture authorization (November 5, 2026)

- Direct `POST /api/paypal/capture` no longer marks a record `capturing`
  just because it is locally `created`. It first GETs that exact order
  from PayPal Sandbox and verifies the order ID, `CAPTURE` intent, one
  purchase unit, USD amount and recorded event/participant reference.
- Any unapproved order, malformed provider response or failed GET cannot
  issue a capture, and the local status remains `created`. Only the
  upstream `APPROVED` status can proceed to the transactional local
  `capturing` lock and one capture attempt.
- A remotely `COMPLETED` order with exactly one independently matching
  capture can be reconciled locally without sending another capture
  request. An ambiguous completed response is rejected for investigation.
- Once a capture attempt is recorded, timeouts and invalid outcomes keep
  it locked; a returned buyer URL never bypasses this rule. The browser
  now checks the **existing** order and seeks explicit confirmation
  before requesting a capture.
- Checks are supported by mocked failure, tampering, replay and race
  tests; they do **not** establish current PayPal availability, durable
  database recovery, real funds or verified identities.

## Checkout preflight and fail-closed allocation check (November 5, 2026)

- The protected `GET /api/paypal/checkout-readiness/{event_id}/{person_id}`
  only reads local data and checks PayPal **configuration**, not provider
  availability. It reports non-secret, finite blocker codes and an amount.
  A green result is advisory and not a payment or capture authorization.
- The actual `POST /api/paypal/orders/{event_id}/{person_id}` reuses the
  same local checks *inside the SQLite write transaction* before inserting
  any payment attempt. All participant shares must exactly match the
  deterministic allocator for the current event expenses. A corrupted or
  stale allocation is rejected with HTTP 409 and does not reach PayPal.
- The hosted page asks for explicit confirmation and validates that the
  approval redirect uses HTTPS on the PayPal Sandbox hostname. If a provider
  response times out or has an unexpected redirect, the local lock remains
  and organizers must reconcile that existing attempt rather than retry.
- This is not external settlement verification. The gate cannot make Free
  SQLite durable, guarantee an upstream order did not exist before a reset,
  or replace independent identities or real financial controls.

## Public guided judge walkthrough (November 5, 2026)

- `/judge` is deliberately public, uses a static five-stage walkthrough and
  keeps review checkmarks only in page memory. It does not store tokens,
  credentials, participant data, or payment results in persistent browser
  storage, and cannot submit a Devpost entry or trigger a capture.
- The optional source check issues `GET /health` with `credentials: omit`,
  verifies the sandbox-only response shape, and reports the source commit
  prefix. This is a **source-version availability diagnostic only**, not an
  upstream PayPal/Gemini test, consent attestation or payment proof.
- The guide clearly separates public browser simulation, bearer-link
  participant consent, protected Gemini integration, and optional PayPal
  Sandbox buyer checkout. It contains no secret or live-payment credential.
- All sensitive hosted API routes remain protected; the guide does not add
  any new authentication exemption or backend mutation.

 (November 4, 2026)

- Hosted unsafe requests (POST, PUT, PATCH, DELETE) reject a cross-site or same-site `Sec-Fetch-Site` context even when an HTTP Basic password was previously entered. If an `Origin` header is present, it must match the request's exact origin or configured `PUBLIC_BASE_URL` (including scheme and port). Malformed, `null` and misleading lookalike origins fail closed.
- PayPal's `/api/paypal/webhook` remains exempt from the browser-origin check **only** because the server independently verifies the provider's signature before processing events. This does not relax its verification or amount-match rules.
- Authenticated command-line requests without browser Origin/Fetch Metadata headers remain supported. This is browser CSRF defence-in-depth, not a replacement for secure identities, explicit CSRF tokens, strong passwords, or API-level quotas.
- Responses set `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a restrictive `Permissions-Policy`. API responses, the protected workspace, and invitation portal are private and not stored by browser caches.
- Configure `PUBLIC_BASE_URL` to the true HTTPS deployment origin; avoid changing this to arbitrary or untrusted sites. These safeguards are covered by offline regression tests and do not prove that the hosted demo is suitable for real money or real participant data.

## Private-link cost transparency and stale quote checks (November 4, 2026)

- A participant bearer invitee receives **aggregate** cost categories,
  total event budget, split method, participant count, and their own assigned
  share. Individual names or individual shares of other participants, raw
  expense titles, payment-provider identifiers, and organizer credentials
  are not included in the participant overview.
- The quote is generated from current local expense and participant records
  with the deterministic integer-cent allocation algorithm. Approval fails
  with HTTP 409 when the current share allocation is inconsistent—even when
  the caller omits the optional quote object for older API compatibility.
- The browser sends the reviewed `expected_share_cents` and
  `expected_total_cents` in the private-link POST approval. A mismatch
  fails closed with HTTP 409, and the browser refreshes the current details.
  A legacy client may omit this optional quote, but it cannot bypass the
  underlying invitation share check or independent allocation consistency.
- No PayPal call, simulation, payment, or verified identity is created by
  viewing or approving the breakdown. This improves **informed fictional
  consent**, not authorization for a real transfer. Links are bearer secrets;
  never share them publicly.

## Hosted provider request budgets (November 4, 2026)

- When `CIRCLESPLIT_HOSTED=1`, each authenticated shared demo role has a **per-process sliding 60-second window**: 12 total Gemini parse/task-plan attempts, 6 new PayPal Sandbox order attempts, and 30 PayPal status/capture attempts. Separate owner and judge roles have separate budgets. Calls returning provider errors still count toward that budget.
- Requests over budget return `HTTP 429` with a `Retry-After` header; no provider-backed endpoint or financial mutation runs for those blocked requests. Browser cross-origin and unauthenticated requests are rejected **before** they could consume the budget.
- Normal event planning, private invitation/RSVP/agenda endpoints, read-only recovery views and independently signature-verified PayPal webhooks are **not** subject to these cost budgets. Local development mode does not apply them either.
- This is a **demo safeguard**, not production-grade distributed rate limiting. Windows reset when a process restarts, do not coordinate across multiple processes/instances, and cover all users sharing a role together. A genuine public service needs durable account-level quotas, provider-side spend caps, monitoring, and abuse protections.
- Judge demo testers may see a rate-limit message after repeated rapid calls; the response indicates when that provider action can be tried again. Never bypass PayPal's existing uncertain-payment locks merely to work around a 429.

## Private invitation session isolation (November 4, 2026)

- The participant portal now validates the **entire URL fragment** as exactly one `token` parameter. A malformed, duplicate or extra parameter clears any old saved invitation from that tab rather than silently displaying a different participant's details.
- A newly supplied valid private link takes precedence over a saved tab token. A session refresh may reuse that tab's previous valid link, and successful incoming links work even when browser session storage is disabled.
- The **Forget this invitation on this device** control removes the token from this tab's session storage, hides the participant view and invalidates in-flight view responses so late network replies cannot repopulate private details. The bearer fragment is removed from the browser address bar after reading.
- Forgetting is **local browser cleanup only**, not revocation or deletion on the server. It does not undo an already submitted RSVP, share approval, or an existing PayPal sandbox checkout. Only the organizer can revoke a bearer invitation. This is still capability-link authorization, not verified personal identity.
- The participant portal remains no-index/no-referrer and does not embed the private token in calendar exports, outgoing links or API URL query parameters.

## Global sandbox capture integrity (November 4, 2026)

- Every confirmed PayPal sandbox capture identifier must be **unique across the whole local payment ledger**, not merely within an individual event. SQLite enforces this with a unique partial index for nonempty capture IDs; if legacy records already reuse an identifier, initialization fails closed instead of silently trusting duplicate payments. Inspect and reconcile such records before attempting any migration.
- Direct capture, existing-order reconciliation, and signed PayPal webhook processing now share a **single transactional settlement guard**. A repeat confirmation of the *same capture on the same order* is idempotent. A different capture on a previously completed order, or a capture already claimed by another order, returns a conflict and cannot inflate sandbox funding.
- A provider response with multiple purchase units, multiple captures, malformed identifiers or mismatched USD amounts is **ambiguous** and cannot mark a local payment completed. Capture attempts that have an uncertain outcome remain locked, and the organizer must check the **existing** PayPal order, never blindly create another order or retry a charge.
- These rules apply to **mocked CI scenarios** and local sandbox database state. They do **not** replace PayPal as the external source of truth, persistent event logs, refund/dispute processing, or a live merchant reconciliation system.

## Participant-controlled approval withdrawal (November 4, 2026)

- An invited participant holding a valid, unexpired private bearer link can explicitly withdraw approval of their **current fictional, unpaid share**, even when the organizer demo previously approved it. The server records the withdrawal without changing payment records.
- The withdrawal flag persists across RSVP updates and budget recalculations. New PayPal Sandbox orders, simulated contributions and organizer demo approvals are blocked while it is present; only a fresh private-link approval clears the flag. An event budget edit still revokes its old invitation, so the organizer must issue a replacement before the participant can approve again.
- Withdrawing is refused once any payment order has been initiated or any simulated contribution has been recorded; it cannot undo or refund a PayPal transaction. The portal displays whether sandbox checkout has already started, and disables the withdrawal control then.
- This is **capability-link consent in a fictional shared sandbox**, not verified human identity, legal consent evidence, recurring mandate management, or a real-money chargeback process. Whoever holds the current invitation token can act on behalf of the fictional participant. A shared judge organizer login still has other broad privileges.

## Storage reset and checkout safety (November 4, 2026)

- Render's Free web-service filesystem is ephemeral. The local SQLite ledger,
  including idempotency keys and PayPal Sandbox reconciliation records, can
  disappear on restart, spin-down or redeployment. This is **not** fixed by a
  normal planning backup or by an environment variable alone.
- A private database incarnation ID and creation time are stored in SQLite.
  The protected readiness API and workspace show a truncated 12-character ID
  that changes after database replacement. This detects local resets, not
  incomplete or missing external PayPal transactions.
- `CIRCLESPLIT_PERSISTENT_MOUNT` can identify an actual non-root filesystem
  mount. The application verifies that the SQLite file is inside that mount;
  setting this variable by itself never proves persistence.
- If `CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB=1` is enabled, the server
  refuses new PayPal Sandbox orders with HTTP 503 **before** recording a payment
  or contacting PayPal unless the mount is verified. Existing order status
  checks, prior capture attempts and signature-verified webhooks remain
  available for safe reconciliation.
- The gate is off by default to preserve the current Free hackathon test flow.
  Enabling it on the current Free service will block new checkout. The optional
  paid Render disk blueprint has **not** been applied. See
  [persistent storage operations](PERSISTENT_STORAGE.md).
- A mounted SQLite file still needs external backups, restore tests, strict
  instance ownership and an identity model before real users. Never claim that
  this diagnostic creates durable storage, real bank accounts, or true escrow.

## Aggregated local Sandbox recovery-risk overview (November 5, 2026)

`GET /api/paypal/recovery` includes a protected read-only `risk` summary
calculated over the **entire current local SQLite ledger**, independent of
its paginated order list. The status categories distinguish known-created
orders, ambiguous order-creation attempts, previously attempted captures,
and malformed/inconsistent local records. There is **no remote provider
lookup, mutation, reconciliation, or retry**. Reported unverified request
face value is not collected or lost money; a payment may exist upstream even
if its local database record has vanished. Exceeding the 60-minute age
threshold never permits automatic duplicate order/capture requests.

The summary uses aggregate counts only and never includes account details,
participant names, approval tokens, request IDs, provider order IDs, or
capture IDs. It inherits the existing hosted organizer Basic-auth and
no-store security policy. A clean local overview cannot prove actual PayPal
settlement or durable offsite storage.

## Complete PayPal Sandbox recovery queue (November 4, 2026)

- The owner/judge-authenticated `GET /api/paypal/recovery` now derives category totals and `attention_count` from **all local payment records**, never just a truncated response. Previously, it counted only the newest 200 rows and could understate unresolved payment attempts.
- The read-only queue prioritizes unresolved or inconsistent records **before** completed captures regardless of age, then sorts by latest local record ID. Orphaned records (a missing event or participant) remain visible as **manual review** rather than disappearing because of an inner join.
- `?limit=50&offset=0` paginates records (1–200 per request) with `next_offset` and the total count. The protected organizer Activity page provides Previous/Next controls, full-ledger status totals and the current page range.
- Existing creation timeouts remain manual-review-only. A `capturing` payment can only initiate an existing-order **status check**, never automatic recapture. No PayPal provider calls, new checkout requests or payment mutations are performed by this endpoint.
- Pagination is over the local, potentially temporary SQLite database. New webhook or payment writes between page requests can shift offset-based pages; refresh from the first page if data changes. These counters are **not** proof of external settlement, receipts or durable records.

## Private sandbox reconciliation manifest (November 4, 2026)

- The organizer-only `GET /api/paypal/reconciliation-export` endpoint returns
  an **explicitly requested, read-only, complete local snapshot** for manual
  PayPal Sandbox review, not payment creation/capture. It includes current
  local payment IDs, fictional event and participant associations, amounts,
  statuses, dates, known PayPal order/capture IDs, and database incarnation.
  Orphaned rows are retained with null names.
- The snapshot **never** includes bearer invitation tokens, token hashes,
  provider API keys, internal request/capture idempotency secrets or raw webhook
  events. It does include private participant names and provider IDs; **never
  share, commit, post publicly or email without appropriate protection**.
- Separately enabled guest-judge credentials are explicitly forbidden from accessing this export. The response uses no-store/private headers, download disposition, a
  schema-specific `kind`, `importable: false`, and a SHA-256 digest of the
  record array. The digest can detect accidental content changes but **is
  not authenticated or a proof of PayPal payment**. The planning restore API
  rejects the manifest, and CircleSplit has no payment import path.
- The server refuses an export with more than 10,000 local payment rows
  rather than silently excluding them. No automatic periodic backups or
  offsite copies have been created. A local snapshot cannot show PayPal
  orders lost from SQLite before it was downloaded.
- A manual reviewer must verify orders against PayPal Sandbox externally
  and investigate unknown order IDs or ambiguous captures. Never treat this
  file as authorization to retry a charge or override financial locks.

## Local-only comparison of two payment reconciliation manifests (November 4, 2026)

- The private Activity page now accepts two locally selected, schema-versioned
  PayPal Sandbox reconciliation JSON files (earlier/later). JavaScript validates
  their server-exported SHA-256 record digests via the Web Crypto API and
  compares records **locally in the browser**. File contents are not uploaded,
  transmitted to PayPal, stored in browser persistence or written to the DB.
  Selected file handles are cleared after the comparison.
- Matching uses local payment IDs **only when** both files have the same
  database incarnation. If their incarnations differ, local IDs may be reused:
  the tool instead matches known PayPal Sandbox order IDs and separately
  counts earlier order attempts whose order ID was never recorded.
- The result displays aggregate missing/new/matched record references,
  completed-status regressions, capture identifier changes, amount changes,
  and safe metadata changes. It never displays participant names or raw order,
  capture, invitation or provider credential values. Unexpected schemas,
  duplicate local/provider order IDs, digest mismatches, oversized files and
  reversed dates fail closed.
- The digest detects **accidental change only**, not who generated the file.
  A matching order ID is not confirmation of payment, and absent orders may
  still exist at PayPal. This is not a real-money reconciliation engine,
  signature validation, refund process, backup service or reason to retry
  payment creation/capture. Manually investigate against PayPal Sandbox.

## Global read-only payment integrity audit (November 4, 2026)

- Authenticated `GET /api/paypal/ledger-audit` scans all current local
  PayPal Sandbox payment rows and participant references without contacting
  PayPal or modifying records. It counts inconsistencies across the entire
  DB but caps individual findings at 100 to bound response size.
- Checks include missing event/participant, cross-event linkage, mismatched
  share amounts, missing or unexpectedly present capture IDs, conflicting
  participant payment states, repeated orders for a participant and unknown
  local statuses. Findings identify only local numeric IDs, not names or
  credentials. Duplicate capture IDs are also scanned defensively, while the
  unique database index remains the primary write-time safeguard.
- A payment in a pending/creating/capturing state is **not automatically an
  integrity issue**. Unresolved orders are counted separately. Use the
  existing recovery queue to inspect known orders or manually investigate
  creation uncertainty; no automatic charge or capture retry is allowed.
- No local audit can prove PayPal external settlement, receipt authenticity,
  absence of upstream orders lost during a SQLite reset, or verified human
  identity. A green result is local consistency only, never a merchant
  accounting sign-off or permission to retry a payment.

## Money invariants

- All allocation arithmetic uses integer cents.
- PayPal amount is read from persisted, approved server data, not the browser.
- Explicit participant withdrawal persists across budget recalculations and prevents new sandbox checkout until renewed private-link consent.
- Budget changes invalidate approvals unless payment activity already exists; then editing is locked.
- A participant's second order is rejected if any payment request already exists.
- Idempotency request IDs are persisted before the PayPal API request.
- Only an exact USD COMPLETED, single-purchase-unit PayPal capture changes sandbox payment status.
- A capture identifier is unique across all events and orders, including concurrent webhook/reconciliation paths.
- Sandbox-paid and simulated-paid amounts are separate in API and UI.
- PayPal request timeout can leave a pending order creation locked for manual reconciliation; NEVER clear the lock or retry a charge blindly.

## Known risks before real users

1. No individual identity or participant-specific consent enforcement; implement authentication/authorization and audit trails.
2. Public shared judge password offers limited isolation; rotate after judging.
3. SQLite ephemeral free-hosting storage is not durable; migrate to managed Postgres for anything beyond a throwaway demo.
4. No automated timeout reconciliation, retry backoff, or complete charge/dispute lifecycle.
5. Hosted per-process provider budgets are not distributed account-level rate limiting, broad abuse controls, cross-account tenancy, or production-grade monitoring.
6. No currency and locale abstraction; USD sandbox and two-decimal currency assumption only.
7. AI suggestions can be incorrect or manipulated by adversarial text; humans must verify amounts and allocations.
8. No merchant fee, refunds, disputes, cross-border compliance, or tax support. Do not call this escrow.

Never commit PAYPAL_CLIENT_SECRET, GEMINI_API_KEY, DEMO_PASSWORD or other credentials. Use cloud environment variables; rotate compromised keys immediately.
