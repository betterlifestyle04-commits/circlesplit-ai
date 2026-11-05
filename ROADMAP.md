# Roadmap and verification status

This document distinguishes implemented code, recorded one-off sandbox checks, and work that remains. CircleSplit is a hackathon prototype, **not** a real-money product.

## Implemented and covered by automated tests
- [x] Responsive public browser-local guest demo and Basic-auth protected organizer workspace
- [x] Public browser-local Resilience Lab with exact-cent no-show and replacement preview, accessible demo tab and judge instructions, no provider network access (November 5, 2026)
- [x] Public guided judge navigation, local-only progress, copyable fictional prompt and source-only health checks (November 5, 2026)
- [x] Protected Scenario Lab affordability targets: minimum additional attendees to keep all exact-cent equal/weighted shares under a chosen cap, without modifying approvals or Sandbox records (November 5, 2026)
- [x] Protected Scenario Lab no-show stress test with exact-cent attendance sensitivity curve, cap-breach alert and no payment or approval mutations (November 5, 2026)
- [x] No-show recovery suggestions: bounded exhaustive exact-cent search for the minimum extra fictional attendees restoring a per-person target, with explicit infeasibility and group-size limits (November 5, 2026)
- [x] Exact-cent equal/weighted group allocation, event planning and expense/participant CRUD
- [x] Explicit share approvals, consent invalidation after budget edits, separate simulations
- [x] Participant-visible aggregate cost explanation and stale-share consent guard (November 4, 2026)
- [x] Private expiring/revocable bearer invitation links, RSVP, individual approvals and agenda review acknowledgements (not identity proof)
- [x] Participant tab invitation switching and explicit session cleanup, with stale response protection (November 4, 2026)
- [x] Private-link withdrawal of share approval, persistent opt-out gate and renewed consent before new sandbox checkout
- [x] Agenda editor, optional private .ics calendar exports with floating local times, event preparation checklists
- [x] Budget breakdown, closeout/integrity reports, backup/restore of unpaid planning data
- [x] Read-only checkout prerequisite diagnostics and transactional full-event allocation recheck before new Sandbox order (November 5, 2026)
- [x] Fresh upstream buyer-approval and exact-order verification before capture; buyer return only reconciles known orders (November 5, 2026)
- [x] PayPal SANDBOX OAuth, Orders v2 create/capture, strict server-side amount verification
- [x] Persisted idempotency keys, duplicate-order lockout, signed webhook verification and replay prevention
- [x] Fail-closed in-flight PayPal Sandbox order creation: database incarnation, request-key and row-state compare-and-set, ASCII order-ID and trusted checkout URL validation (November 5, 2026)
- [x] Bound existing-order checks and late capture settlement to original SQLite incarnation and request keys across provider awaits; concurrent capture locks cannot be misreported as new capture permission (November 5, 2026)
- [x] Global unique sandbox capture IDs, shared transactional settlement guard and ambiguous-capture rejection
- [x] Read-only PayPal recovery queue and checks of existing orders; no blind capture retry
- [x] Full-ledger recovery totals, attention-first paginated queue and missing-record investigation safeguards
- [x] Protected, read-only recovery risk overview with all-ledger triage, 60-minute age review and unverified request face value distinct from completed Sandbox captures (November 5, 2026)
- [x] Manual private Sandbox reconciliation JSON export with complete current local ledger, reset epoch, digest and no payment import (November 4, 2026)
- [x] Browser-local, digest-checked comparison of private Sandbox manifests, with reset-aware PayPal order matching and no network upload (November 4, 2026)

- [x] Global read-only ledger consistency audit, bounded numeric findings and distinct unresolved-order counts (November 4, 2026)
- [x] Offline operator SQLite snapshot, SHA-256 and schema verification, standalone WAL handling and isolated no-import recovery rehearsal (November 5, 2026)
- [x] Offline comparison of two authenticated encrypted backup generations with reset-aware provider-order and capture continuity, anonymous regression counts and review-required exit status (November 5, 2026)
- [x] Optional operator-only AES-256-GCM encrypted snapshot container with separate generated key file, authenticated verify and no-restore drill (November 5, 2026)
- [x] Isolated recovery drill runs bounded, anonymous semantic payment-ledger audit and returns distinct review-required exit code (November 5, 2026)
- [x] Browser-local dataset incarnation and capture/webhook count regression warnings, preserving the prior checkpoint until explicit investigation acknowledgement (November 5, 2026)
- [x] Optional Gemini expense and task proposals with human review before any changes
- [x] Hosted cross-origin mutation protections and no-store/private browser security headers (November 4, 2026)
- [x] Hosted 60-second per-role request budgets for Gemini calls, PayPal order creation and PayPal reconciliation (per process; not production quotas)
- [x] Explicit hosted owner/judge permissions: judge-only credentials retain fictional planning and read-only Sandbox diagnostics but cannot create, capture, reconcile provider orders or export private payment manifests (November 5, 2026)
- [x] Public no-cache deployment health endpoint with verified Render Git SHA (source revision only)
- [x] Protected database incarnation ID, verified-mount diagnostic, ephemeral storage warning, and opt-in fail-closed new-checkout guard
- [x] MIT license, setup instructions, offline automated tests and CI

## Provider tests documented from November 2–3, 2026
- [x] **One real Gemini sandbox-demo request:** the README records HTTP 200 for a three-expense proposal totaling $235.00. This is a point-in-time smoke test, not continuous provider availability.
- [x] **One PayPal SANDBOX happy path:** the README records an $11.00 fictional share, test-buyer approval, completed order capture and verified webhook delivery. This is not real revenue or evidence of production readiness.
- [ ] Re-check both live integrations and current ephemeral records immediately before recording the final judging demo.

See the README's **Verified provider smoke test (November 2–3, 2026)** for the evidence and limitations. Automated tests mock the payment provider and do not independently verify live credentials or today's deployment.

## Remaining before final submission
- [ ] Individual organizer and participant accounts/roles and real identity-bound consent; shared judge Basic credentials and bearer links are limited substitutes
- [ ] Actually provision durable storage and regular external backups, test recovery, and add distributed abuse/rate limits and individual tenancy isolation for real users
- [ ] Automated reconciliation after ambiguous upstream timeouts; do not retry an uncertain charge automatically
- [ ] Compare live /health git_commit with main SHA and verify public demo in incognito; distribute judge credentials only privately
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
