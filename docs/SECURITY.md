# Security and operational boundaries

This repo is a hackathon **prototype**, not an online payment platform. All user and event data is fictional. All PayPal API traffic goes to the SANDBOX endpoint. No production PayPal payments are supported.

## Trust assumptions

- Local development defaults to a single trusted organizer with no accounts.
- CIRCLESPLIT_HOSTED=1 makes the app require a shared judge password (HTTP Basic auth). Without a 12+ character DEMO_PASSWORD, the hosted app responds with HTTP 503 (fail-closed).
- Shared judge credentials are **not** secure individual participant identities. Any authenticated judge can operate the organizer demo.
- The PayPal webhook is exempt from judge Basic auth because PayPal cannot send judge credentials, but its signature must be verified by PayPal before any state change.

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
5. No rate limits, abuse controls, proper cross-account tenancy, nor production-grade monitoring.
6. No currency and locale abstraction; USD sandbox and two-decimal currency assumption only.
7. AI suggestions can be incorrect or manipulated by adversarial text; humans must verify amounts and allocations.
8. No merchant fee, refunds, disputes, cross-border compliance, or tax support. Do not call this escrow.

Never commit PAYPAL_CLIENT_SECRET, GEMINI_API_KEY, DEMO_PASSWORD or other credentials. Use cloud environment variables; rotate compromised keys immediately.
