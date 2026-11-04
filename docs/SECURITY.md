# Security and operational boundaries

This repo is a hackathon **prototype**, not an online payment platform. All user and event data is fictional. All PayPal API traffic goes to the SANDBOX endpoint. No production PayPal payments are supported.

## Trust assumptions

- Local development defaults to a single trusted organizer with no accounts.
- CIRCLESPLIT_HOSTED=1 makes the app require a shared judge password (HTTP Basic auth). Without a 12+ character DEMO_PASSWORD, the hosted app responds with HTTP 503 (fail-closed).
- Shared judge credentials are **not** secure individual participant identities. Any authenticated judge can operate the organizer demo.
- The PayPal webhook is exempt from judge Basic auth because PayPal cannot send judge credentials, but its signature must be verified by PayPal before any state change.


## Hosted browser safeguards (November 4, 2026)

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
