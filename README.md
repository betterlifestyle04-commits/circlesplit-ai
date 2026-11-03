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
