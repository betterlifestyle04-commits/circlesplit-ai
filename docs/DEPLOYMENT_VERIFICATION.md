# Verifying the live Render deployment

The public `GET /health` endpoint now returns the deployed Git commit fingerprint
from Render's automatically supplied `RENDER_GIT_COMMIT` environment variable.

Sample response (illustrative, not a live result):

```json
{"status":"ok","mode":"sandbox-only","version":"0.2.0","git_commit":"0123456789abcdef0123456789abcdef01234567"}
```

## Public browser CSP validation

The automatic main-branch gate checks CSP on all three anonymously
served entry pages: public planner (`/`), judge guide (`/judge`)
and the invitation portal (`/participant`). It independently
hashes the **actual served** inline JavaScript in both the planner and
invitation portal and compares each with its `script-src 'sha256-…'`.
It rejects `unsafe-inline`, `unsafe-eval`, missing frame/base/form
protections, or broader `connect-src` permissions. The public planner
cannot use browser network APIs; the judge guide and participant
portal can reach only same-origin endpoints.

The invitation portal also requires `private, no-store` caching and
`Referrer-Policy: no-referrer` to prevent shared-cache or referral
exposure of invitation metadata. This confirms served policy/source
consistency—not that all interactive browser flows were executed, nor
that the organizer workspace has a strict CSP. Embedded CSS still
uses inline style allowances.

## Judge arithmetic module loading and self-check UI

In addition to hash-authenticated public scripts, the release gate
requires the public `/judge` document to load the audited
`/static/public_recovery.js` arithmetic module **before**
`/static/judge_walkthrough.js`. It also checks that the run button
and accessible results status remain present. Missing or misordered
resources cause an immediate non-retryable release failure rather
than presenting a broken self-check to judges.

These live checks validate HTTP output and static script ordering.
The actual five example calculations and isolated browser UI behavior
are tested in the separate Node suite. Neither proves actual Gemini
model access, PayPal provider reachability, judge credential validity
or the durability of the ephemeral database.

## Automatic checks on main

A GitHub Actions job named **Live public release and authentication
gate** runs after the full Python/JavaScript test suite on a
`main` push. It verifies the exact deployed commit (with bounded
retry while Render rolls out), three public pages, four public
JavaScript assets, and unauthorized access behavior on private
organizer/static/payment-diagnostic routes. It sends no credentials
and **only anonymous GET** requests, following no redirects.

You can rerun it on `main` from the workflow's **Run workflow**
control, or run it locally:

```bash
python tools/verify_live.py --expected-sha "$(git rev-parse origin/main)" --attempts 30 --delay 8
```

Pass means the selected revision is live and these public/static
authorization conditions hold. Failure is actionable: a stale SHA
or temporary 503 can reflect a rollout; HTTP 200 on a protected
route is a security problem requiring investigation. The script
does not perform actual PayPal orders/captures or verify AI Gemini,
signed webhooks, browser session behavior, login with credentials,
or persistent storage.

**Operational limitation:** Render deploys directly from GitHub
before the live-gate job can finish; a failed GitHub check does not
automatically prevent or roll back the Render release. Do not give
judges a green-light until both unit tests **and** this live gate
pass, and complete credentialed/real-browser review separately.

## How to verify

1. Find the latest commit SHA on [the repository's main branch](https://github.com/betterlifestyle04-commits/circlesplit-ai/commits/main), or run `git rev-parse origin/main`.
2. Open [the deployed health endpoint](https://circlesplit-ai-demo.onrender.com/health). It is public and contains no API keys, passwords, payment IDs, or participant data.
3. Compare the **full 40-character** `git_commit` value with the SHA from step 1. If they match, the service reports that it is running the selected repository revision. If they differ, Render may be behind or configured against another commit/branch. Verify the service's GitHub repository, branch and deployment history in Render.
4. If `git_commit` is `null`, the service has no valid Render commit metadata. Do not assume it is current; check Render deployment settings and logs.
5. Confirm the latest GitHub Actions test suite is green and test the public homepage, protected organizer workspace, participant portal, Gemini proposal and PayPal SANDBOX flow separately.

`/health` is marked `no-store` to avoid a cached previous revision.
The presence of a commit hash **does not** prove the current database is durable,
PayPal and Gemini are connected, webhooks are configured, or judges can log in.
It identifies deployed source code, not full functional readiness.

Render documents `RENDER_GIT_COMMIT` as a built-in runtime environment variable:
https://render.com/docs/environment-variables

**IMPORTANT:** The app is a sandbox-only, fictional-data hackathon prototype.
Do not place secrets or live payment credentials in this health response.
