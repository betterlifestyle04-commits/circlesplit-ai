#!/usr/bin/env python3
"""Real Chromium smoke for local and strictly read-only hosted judge pages.

A disposable localhost test also checks the private HTTP 401 boundary.
The hosted mode is tied to a single trusted HTTPS origin and exact commit SHA.
No account, PayPal, Gemini, payment, write request, or real data is involved.
Playwright is test-only and is never installed in the Render runtime.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import urlopen

from verify_live import DEFAULT_ORIGIN, request_once, valid_sha

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_BROWSER_PATHS = frozenset((
    "/", "/judge", "/favicon.ico",
    "/static/public_recovery.js", "/static/public_portability.js",
    "/static/public_scenarios.js", "/static/judge_walkthrough.js",
))


def permitted_browser_request(origin, url, method, *, hosted=False):
    """Pure fail-closed network policy used by both Chromium smoke modes."""
    base, target = urlsplit(origin), urlsplit(url)
    if (method != "GET" or target.scheme != base.scheme or
            target.hostname != base.hostname or target.port != base.port or
            target.username is not None or target.password is not None or
            target.fragment or target.query):
        return False
    if target.path.startswith("/api/"):
        return False
    if hosted and target.path not in PUBLIC_BROWSER_PATHS:
        return False
    return True


def verify_hosted_revision(expected_sha, fetch=request_once):
    """Read only, exact-origin, no-redirect health verification pre/post UI."""
    if not valid_sha(expected_sha):
        raise ValueError("Hosted browser smoke needs the full expected 40-hex commit")
    response = fetch(DEFAULT_ORIGIN + "/health", method="GET", timeout=12.0)
    require(response.status == 200, "Hosted /health did not return HTTP 200")
    try:
        health = json.loads(response.body)
    except (ValueError, UnicodeError) as exc:
        raise AssertionError("Hosted /health response is not JSON") from exc
    require(isinstance(health, dict) and health.get("status") == "ok" and
            health.get("mode") == "sandbox-only",
            "Hosted /health did not report healthy sandbox-only mode")
    require(health.get("git_commit") == expected_sha,
            "Hosted revision does not match the exact CI commit")



def require(condition, message):
    if not condition:
        raise AssertionError(message)


def run_chromium_smoke(origin, *, hosted=False):
    # The browser exercises actual HTML, JS, CSP and DOM interactions, rather
    # than the synthetic DOM shim used by the fast Node controller tests.
    from playwright.sync_api import expect, sync_playwright

    errors = []
    blocked_urls = []
    suspicious_requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, args=["--no-sandbox"])
        try:
            context = browser.new_context(
                viewport={"width": 1365, "height": 900},
                permissions=["clipboard-read", "clipboard-write"],
                service_workers="block", accept_downloads=False,
            )
            def route_request(route):
                request = route.request
                if not permitted_browser_request(
                        origin, request.url, request.method, hosted=hosted):
                    # Record only a fixed diagnostic category, never an
                    # accidentally constructed credential-bearing URL.
                    if urlsplit(request.url).path.startswith("/api/"):
                        suspicious_requests.append("organizer API request")
                    else:
                        blocked_urls.append("unapproved browser request")
                    route.abort()
                    return
                route.continue_()
            context.route("**/*", route_request)
            page = context.new_page()
            page.set_default_timeout(12000)
            page.on("pageerror", lambda error: errors.append(str(error)))

            response = page.goto(origin + "/", wait_until="load")
            require(response is not None and response.status == 200,
                    "Public demo must load HTTP 200 in real Chromium")
            require(page.locator("#kEvents").inner_text() == "1",
                    "Seeded public event was not rendered")
            require(page.locator("#kBudget").inner_text() == "$220.00",
                    "Public demo seeded budget was not computed")
            require(page.locator("#compare-copy-summary").is_disabled(),
                    "Anonymous summary must start disabled")
            # Real browsers enforce visibility: the planner lives in a
            # different tab rather than the initially visible Overview.
            page.locator('button[data-view="events"]').click()
            require(page.locator("#events").is_visible(),
                    "Event Planner navigation did not reveal the tab")
            page.locator("#duplicate-event").click()
            require(page.locator("#compare-copy-summary").is_enabled(),
                    "Duplicate scenario did not enable validated copy control")
            require(page.locator("#cmp-over-before").inner_text() == "0",
                    "Equal baseline above-cap count was incorrect")
            page.locator("#weighted").click()
            require(page.locator("#cmp-over-after").inner_text() == "4",
                    "Weighted $220 / 20-person scenario did not show 4 above $12")
            require(page.locator("#cmp-excess-after").inner_text() == "$6.33",
                    "Weighted scenario did not show $6.33 maximum excess")
            page.locator("#compare-copy-summary").click()
            expect(page.locator("#compare-copy-status")).to_contain_text("copied")
            copied = page.evaluate("navigator.clipboard.readText()")
            require("FICTIONAL browser-only scenario summary" in copied,
                    "Browser copy did not include clearly labeled fictional evidence")
            require("above cap 4/20; maximum excess $6.33" in copied,
                    "Browser copy did not match the visible verified scenario")
            require("NOT VERIFIED: real affordability" in copied,
                    "Copied summary omitted mandatory provider/evidence disclaimer")
            for forbidden in ("Friday Community Volleyball", "Court rental",
                              "Alex", "Taylor", "Sam", "order_id", "capture_id",
                              "demo_paid"):
                require(forbidden not in copied,
                        "Copied comparison included private/fictional identity or payment state")
            page.locator("#compare-share-cap").fill("12.999")
            require(page.locator("#compare-copy-summary").is_disabled(),
                    "Invalid share cap did not disable the copy action")
            require(page.locator("#cmp-budget-before").inner_text() == "$220.00",
                    "Invalid threshold incorrectly cleared independent budget metrics")

            response = page.goto(origin + "/judge", wait_until="load")
            require(response is not None and response.status == 200,
                    "Public judge guide must load HTTP 200")
            require(page.locator("#judge-copy-evidence").is_disabled(),
                    "Judge local-math proof copy must start disabled")
            page.locator("#judge-run-local-tests").click()
            require(page.locator("#judge-math-status").inner_text().startswith("PASS: 5/5"),
                    "Actual Chromium judge arithmetic checks did not all pass")
            lines = page.locator("#judge-math-results").inner_text().splitlines()
            require(len(lines) == 5 and all(line.startswith("PASS") for line in lines),
                    "Actual Chromium judge result rows are missing or failed")
            require(page.locator("#judge-copy-evidence").is_enabled(),
                    "Valid judge local arithmetic did not enable copy")
            page.locator("#judge-copy-evidence").click()
            expect(page.locator("#judge-copy-evidence-status")).to_contain_text("copied")
            copied = page.evaluate("navigator.clipboard.readText()")
            require("browser-only" in copied.lower() and "5/5" in copied,
                    "Copied judge proof is not explicitly limited to local math")
            require("PayPal" in copied and "Gemini" in copied,
                    "Copied judge proof omitted provider verification limits")

            # APIRequestContext checks the HTTP Basic boundary without
            # triggering a browser-native username/password prompt.
            response = context.request.get(origin + "/workspace")
            require(response.status == 401,
                    "Protected workspace was available to anonymous Chromium")
            require(not suspicious_requests,
                    "Public browser made an organizer/API request unexpectedly")
            require(not blocked_urls,
                    "Public browser attempted an external request")
            require(not errors,
                    "Actual browser reported a JavaScript error: " + "; ".join(errors[:2]))
            print("PASS: real Chromium public planner and judge math, clipboard, "
                  "validation, CSP scripts and anonymous workspace boundary")
            print("Scope: "+("verified hosted HTTPS origin" if hosted else "localhost")+
                  ", fictional data, GET-only browser requests, no providers or credentials")
        finally:
            browser.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hosted-read-only", action="store_true",
                        help="Check deployed public pages against exact known Render SHA")
    parser.add_argument("--expected-sha", default=None,
                        help="40-hex revision required in hosted mode")
    args = parser.parse_args(argv)
    if args.hosted_read_only:
        if not valid_sha(args.expected_sha):
            parser.error("--hosted-read-only requires --expected-sha with 40 hex characters")
        verify_hosted_revision(args.expected_sha)
        run_chromium_smoke(DEFAULT_ORIGIN, hosted=True)
        verify_hosted_revision(args.expected_sha)
        print("PASS: hosted real-Chromium public demo and judge, exact deployed revision, "
              "no remote writes, provider credentials or private data")
        return 0
    if args.expected_sha:
        parser.error("--expected-sha is valid only with --hosted-read-only")
    # Start a local production app with hosted auth boundaries and throwaway DB.
    with tempfile.TemporaryDirectory(prefix="circlesplit-chromium-") as temp:
        env = os.environ.copy()
        env["CIRCLESPLIT_DB"] = str(Path(temp) / "smoke.sqlite3")
        env["CIRCLESPLIT_HOSTED"] = "1"
        env["DEMO_USERNAME"] = "browser-smoke-owner"
        env["DEMO_PASSWORD"] = "browser-smoke-standalone-long-password"
        env["JUDGE_ACCESS_ENABLED"] = "0"
        # Never send actual configured cloud credentials to this local app.
        for key in ("PAYPAL_CLIENT_ID", "PAYPAL_CLIENT_SECRET", "PAYPAL_WEBHOOK_ID",
                    "GEMINI_API_KEY", "JUDGE_PASSWORD", "CIRCLESPLIT_BACKUP_KEY"):
            env.pop(key, None)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        origin = "http://127.0.0.1:" + str(port)
        with open(Path(temp) / "server.log", "w+", encoding="utf-8") as logfile:
            proc = subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app:app", "--host",
                 "127.0.0.1", "--port", str(port), "--no-access-log"],
                cwd=ROOT, env=env, stdout=logfile, stderr=subprocess.STDOUT,
            )
            try:
                ready = False
                for _ in range(90):
                    require(proc.poll() is None,
                            "Temporary hosted smoke server exited before startup")
                    try:
                        with urlopen(origin + "/health", timeout=0.5) as response:
                            if response.status == 200:
                                ready = True
                                break
                    except (URLError, TimeoutError, OSError):
                        time.sleep(0.15)
                require(ready, "Temporary hosted app did not become ready")
                run_chromium_smoke(origin)
            finally:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)


if __name__ == "__main__":
    main()
