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

## Hosted provider request budgets (November 4, 2026)

- When `CIRCLESPLIT_HOSTED=1`, each authenticated shared demo role has a **per-process sliding 60-second window**: 12 total Gemini parse/task-plan attempts, 6 new PayPal Sandbox order attempts, and 30 PayPal status/capture attempts. Separate owner and judge roles have separate budgets. Calls returning provider errors still count toward that budget.
- Requests over budget return `HTTP 429` with a `Retry-After` header; no provider-backed endpoint or financial mutation runs for those blocked requests. Browser cross-origin and unauthenticated requests are rejected **before** they could consume the budget.
- Normal event planning, private invitation/RSVP/agenda endpoints, read-only recovery views and independently signature-verified PayPal webhooks are **not** subject to these cost budgets. Local development mode does not apply them either.
- This is a **demo safeguard**, not production-grade distributed rate limiting. Windows reset when a process restarts, do not coordinate across multiple processes/instances, and cover all users sharing a role together. A genuine public service needs durable account-level quotas, provider-side spend caps, monitoring, and abuse protections.
- Judge demo testers may see a rate-limit message after repeated rapid calls; the response indicates when that provider action can be tried again. Never bypass PayPal's existing uncertain-payment locks merely to work around a 429.

## Money invariants

- All allocation arithmetic uses integer cents.
- PayPal amount is read from persisted, approved server data, not the browser.
- Budget changes invalidate approvals unless payment activity already exists; then editing is locked.
- A participant's second order is rejected if any payment request already exists.
- Idempotency request IDs are persisted before the PayPal API request.
- Only an exact USD COMPLETED PayPal capture changes sandbox payment status.
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
