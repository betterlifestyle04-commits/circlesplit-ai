# Verifying the live Render deployment

The public `GET /health` endpoint now returns the deployed Git commit fingerprint
from Render's automatically supplied `RENDER_GIT_COMMIT` environment variable.

Sample response (illustrative, not a live result):

```json
{"status":"ok","mode":"sandbox-only","version":"0.2.0","git_commit":"0123456789abcdef0123456789abcdef01234567"}
```

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
