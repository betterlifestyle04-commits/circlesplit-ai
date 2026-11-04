# Roadmap and verification status

This document distinguishes implemented code, recorded one-off sandbox checks, and work that remains. CircleSplit is a hackathon prototype, **not** a real-money product.

## Implemented and covered by automated tests
- [x] Responsive public browser-local guest demo and Basic-auth protected organizer workspace
- [x] Exact-cent equal/weighted group allocation, event planning and expense/participant CRUD
- [x] Explicit share approvals, consent invalidation after budget edits, separate simulations
- [x] Private expiring/revocable bearer invitation links, RSVP, individual approvals and agenda review acknowledgements (not identity proof)
- [x] Agenda editor, optional private .ics calendar exports with floating local times, event preparation checklists
- [x] Budget breakdown, closeout/integrity reports, backup/restore of unpaid planning data
- [x] PayPal SANDBOX OAuth, Orders v2 create/capture, strict server-side amount verification
- [x] Persisted idempotency keys, duplicate-order lockout, signed webhook verification and replay prevention
- [x] Read-only PayPal recovery queue and checks of existing orders; no blind capture retry
- [x] Optional Gemini expense and task proposals with human review before any changes
- [x] Hosted cross-origin mutation protections and no-store/private browser security headers (November 4, 2026)
- [x] MIT license, setup instructions, offline automated tests and CI

## Provider tests documented from November 2–3, 2026
- [x] **One real Gemini sandbox-demo request:** the README records HTTP 200 for a three-expense proposal totaling $235.00. This is a point-in-time smoke test, not continuous provider availability.
- [x] **One PayPal SANDBOX happy path:** the README records an $11.00 fictional share, test-buyer approval, completed order capture and verified webhook delivery. This is not real revenue or evidence of production readiness.
- [ ] Re-check both live integrations and current ephemeral records immediately before recording the final judging demo.

See the README's **Verified provider smoke test (November 2–3, 2026)** for the evidence and limitations. Automated tests mock the payment provider and do not independently verify live credentials or today's deployment.

## Remaining before final submission
- [ ] Individual organizer and participant accounts/roles and real identity-bound consent; shared judge Basic credentials and bearer links are limited substitutes
- [ ] Durable storage, backup/restore of provider reconciliation data, abuse/rate limits and tenancy isolation for real users
- [ ] Automated reconciliation after ambiguous upstream timeouts; do not retry an uncertain charge automatically
- [ ] Public-demo final verification in an incognito browser; judge credentials distributed only via a private submission field
- [ ] Public YouTube demonstration under three minutes with no credentials or identifiable buyer details
- [ ] Final Devpost submission and explicit eligibility confirmation

## Competition milestones
Hackathon documentation records an early eligibility check on **November 5, 2026** and a final deadline of **November 12, 2026 at 12:00 PT**. Confirm on the event's official rules before relying on these dates.

## Non-negotiable architecture constraints
- All PayPal traffic is SANDBOX-only. No live charges, payouts, escrow, taxes or refunds.
- A settled sandbox contribution requires an exact matching, completed provider capture ID; a participant status flag alone is never proof.
- The organizer demo is shared and uses fictional data. A linked participant is not identity verified.
- AI is strictly advisory and cannot spend or mutate budgets without explicit organizer confirmation.
- An ambiguous order-creation or capture response must remain locked until reconciled; never clear payment locks blindly.
- Calendar exports use floating local wall-clock times because the app does not store a verified event timezone.
