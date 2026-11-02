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

## Safety and demo limitations

The MVP uses a single locally trusted organizer and **does not yet implement accounts or role-based permissions**. It should run locally (127.0.0.1) and must not be exposed directly to the Internet. AI output is untrusted and cannot initiate payments. Do not claim integration success until you test real sandbox credentials. PayPal orders remain authorization- and identity-sensitive. The project does not act as an escrow, money transmitter, or real payment splitting platform.

## Submission requirements

Official hackathon: https://paypalaihackathon.devpost.com/
Deadline: **November 12, 2026 at 12:00 PM PST**.
The judges require a working demo, public source code under an approved open-source license, documented PayPal + AI integration, and a public YouTube demo **under 3 minutes**. This repo is a work in progress and has not yet met every requirement.

## License

MIT. See [LICENSE](LICENSE).
