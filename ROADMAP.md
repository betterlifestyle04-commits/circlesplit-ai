# Roadmap and verification status

## Built
- [x] Responsive group budgeting interface with dashboard, activity and AI proposal review
- [x] Server-authoritative, deterministic cent-exact equal and weighted splits
- [x] Event/expense/participant CRUD and SQLite persistence
- [x] Explicit share approval; budget changes invalidate prior approval
- [x] Simulated payment path clearly separated from sandbox capture
- [x] PayPal sandbox-only OAuth, Orders v2 and capture code
- [x] Idempotent request keys and duplicate order lockout
- [x] Verified signature webhook processing and replay prevention
- [x] Optional Gemini JSON expense extraction with validation and human approval
- [x] README, MIT license, automated backend tests and GitHub CI

## Not done; do not claim verification
- [ ] Real PayPal sandbox create/approve/capture with merchant + buyer test accounts
- [ ] Verified real Gemini model request
- [ ] Authenticated participant invitations and organizer roles
- [ ] Recovery from ambiguous upstream timeouts and production-grade reconciliation
- [ ] Public judge demo with role isolation, sandbox rate limiting and security review
- [ ] Public YouTube video under three minutes
- [ ] Devpost final submission

## Competition requirements
Primary requirements: meaningful PayPal and AI use, functional demo, public repository with open-source license, clear setup instructions, public YouTube video under three minutes. Early eligibility check: November 5, 2026. Final deadline: November 12, 2026, 12:00 PT.

## Architecture decisions
- Use sandbox transactions exclusively; never store PayPal secrets in repo.
- PayPal source of truth for settled contribution is an exact matching confirmed capture.
- API is **local-trust prototype only**, so never deploy publicly without identity/role controls.
- AI is advisory only, not an autonomous spender.
- If a create-order HTTP call has an ambiguous result, lock participant until manual reconciliation to avoid duplicate charges. TODO: robust automated reconciliation/retry recovery.
