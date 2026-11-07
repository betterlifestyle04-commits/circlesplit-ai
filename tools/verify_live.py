#!/usr/bin/env python3
"""Read-only CircleSplit hosted release gate with zero credentials.

Run: python tools/verify_live.py --expected-sha <full 40-hex git SHA>
Checks source revision, public UI/scripts, and authentication boundaries.
NO sandbox orders, captures, provider requests, logins or database writes.
Uses only Python standard library; redirect-following is disabled.
"""

import argparse
import base64
import hashlib
from dataclasses import dataclass
import json
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_ORIGIN = "https://circlesplit-ai-demo.onrender.com"
MAX_BODY = 256 * 1024

# These are the exact four executable scripts required by the public UI.
# Unit tests assert this list matches security.PUBLIC_DEMO_SCRIPT_PATHS.
PUBLIC_SCRIPTS = {
    "/static/public_recovery.js": "CircleSplitPublicRecovery",
    "/static/public_portability.js": "CircleSplitPublicPortability",
    "/static/public_scenarios.js": "CircleSplitPublicScenarios",
    "/static/judge_walkthrough.js": "Judge",
}
PUBLIC_PAGES = {
    "/": "Compare two fictional plans",
    "/judge": "Judge walkthrough",
    "/participant": "Private participant approval",
}
PRIVATE_PATHS = (
    "/workspace",
    "/api/state",
    "/api/judge-access-readiness",
    "/api/paypal/recovery",
    "/api/paypal/webhook-audit",
    "/api/paypal/reconciliation-export",
    "/static/index.html",
    "/static/participant.html",
    "/static/insights.js",
)


@dataclass(frozen=True)
class Result:
    status: int
    headers: dict
    body: bytes

    def header(self, name):
        return self.headers.get(name.lower(), "")


class ProbeFailure(Exception):
    def __init__(self, problem, *, retryable=False):
        super().__init__(problem)
        self.retryable = retryable


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_base_url(base):
    if not isinstance(base, str) or base != base.strip():
        raise ValueError("Invalid deployment origin")
    value = urlsplit(base)
    if (
        value.scheme != "https" or not value.hostname
        or value.username is not None or value.password is not None
        or value.path not in ("", "/") or value.query or value.fragment
    ):
        raise ValueError("Release checks require a bare HTTPS origin, no credentials")
    try:
        _ = value.port
    except ValueError as exc:
        raise ValueError("Invalid deployment port") from exc
    return base.rstrip("/")


def valid_sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{40}", value) is not None


def request_once(url, method="GET", timeout=10.0):
    """Never send credentials, follow redirects, POST or read unbounded bodies."""
    if method not in ("GET", "HEAD"):
        raise ValueError("Release gate permits only GET and HEAD")
    req = Request(url, method=method, headers={
        "User-Agent": "CircleSplit-ReadOnly-ReleaseGate/1.0",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Accept": "application/json,text/html,application/javascript,text/javascript,*/*",
    })
    try:
        response = build_opener(_NoRedirect()).open(req, timeout=timeout)
    except HTTPError as exc:
        response = exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ProbeFailure("Network failure during anonymous deployment check", retryable=True) from exc
    try:
        status = response.status
        body = response.read(MAX_BODY + 1) if method == "GET" else b""
        if len(body) > MAX_BODY:
            raise ProbeFailure("Anonymous response exceeds safe read limit")
        return Result(status, {key.lower(): val for key, val in response.headers.items()}, body)
    finally:
        response.close()


def _expect(condition, message, *, retryable=False):
    if not condition:
        raise ProbeFailure(message, retryable=retryable)


def _read_text(response, path, expected_type, marker):
    _expect(response.status == 200, f"{path}: expected public HTTP 200, got {response.status}",
            retryable=response.status in (502, 503, 504))
    _expect(expected_type in response.header("content-type").lower(),
            f"{path}: unexpected Content-Type")
    _expect(response.header("x-content-type-options") == "nosniff",
            f"{path}: missing nosniff protection")
    _expect(response.header("x-frame-options") == "DENY",
            f"{path}: missing frame-protection header")
    text = response.body.decode("utf-8", errors="replace")
    _expect(marker in text, f"{path}: required public release marker absent")
    return text


def _verify_public_csp(path, result, html):
    """Independently compare deployed inline-script bytes with strict CSP."""
    csp = result.header("content-security-policy")
    required = (
        "default-src 'none'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'none'",
    )
    for directive in required:
        _expect(directive in csp.split("; ") or directive in
                [part.strip() for part in csp.split(";")],
                f"{path}: missing strict CSP {directive}")
    directives = [p.strip() for p in csp.split(";")]
    scripts = [p for p in directives if p.startswith("script-src ")]
    _expect(len(scripts) == 1 and "'self'" in scripts[0].split(),
            f"{path}: public scripts must use a single same-origin policy")
    script = scripts[0]
    for forbidden in ("'unsafe-inline'", "'unsafe-eval'", "data:", "blob:", "*"):
        _expect(forbidden not in script.split(),
                f"{path}: unsafe public script policy {forbidden}")
    expected_connection = "connect-src 'none'" if path == "/" else "connect-src 'self'"
    _expect(expected_connection in directives,
            f"{path}: incorrect public network policy")
    _expect("no-store" in result.header("cache-control").lower(),
            f"{path}: public HTML must not be cached")
    codes = re.findall(
        r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script\s*>",
        html, flags=re.IGNORECASE | re.DOTALL
    )
    # Enforce that the static public demo contains exactly its one known
    # inline program. Judge guide must have none (only external JS).
    _expect(len(codes) == (1 if path == "/" else 0),
            f"{path}: unexpected number of public inline scripts")
    for code in codes:
        expected_hash = "'sha256-" + base64.b64encode(
            hashlib.sha256(code.encode("utf-8")).digest()
        ).decode("ascii") + "'"
        _expect(expected_hash in script.split(),
                f"{path}: deployed CSP hash does not match inline JavaScript")


def verify_once(base, expected_sha, fetch=request_once, timeout=10.0):
    """One complete, side-effect-free release inspection; never accepts stale SHA."""
    _expect(valid_sha(expected_sha), "A full 40-character expected Git commit is required")
    base = validate_base_url(base)
    observed = []

    def get(path, method="GET"):
        result = fetch(base + path, method, timeout)
        observed.append((method, path, result.status))
        return result

    health = get("/health")
    _expect(health.status == 200, f"/health: HTTP {health.status}",
            retryable=health.status in (502, 503, 504))
    _expect("application/json" in health.header("content-type").lower(),
            "/health: unexpected Content-Type")
    _expect("no-store" in health.header("cache-control").lower(),
            "/health: response must not be cached")
    _expect(health.header("x-content-type-options") == "nosniff",
            "/health: missing nosniff")
    try:
        payload = json.loads(health.body)
    except (ValueError, UnicodeError) as exc:
        raise ProbeFailure("/health: invalid JSON") from exc
    _expect(isinstance(payload, dict) and payload.get("status") == "ok"
            and payload.get("mode") == "sandbox-only",
            "/health: expected healthy sandbox-only deployment")
    current = payload.get("git_commit")
    _expect(valid_sha(current), "/health: missing or invalid deployment revision")
    _expect(current.lower() == expected_sha.lower(),
            f"/health: deployed commit {current} differs from expected {expected_sha.lower()}",
            retryable=True)

    for path, marker in PUBLIC_PAGES.items():
        response = get(path)
        html = _read_text(response, path, "text/html", marker)
        if path in ("/", "/judge"):
            _verify_public_csp(path, response, html)
        elif path == "/participant":
            _expect("frame-ancestors 'none'" in
                    response.header("content-security-policy"),
                    "/participant: missing frame-ancestor protection")
    for path, marker in PUBLIC_SCRIPTS.items():
        response = get(path)
        # Check HTTP status before content-type; 503 is retryable during
        # cold starts, but 404 or an HTML script response is a hard error.
        _read_text(response, path, "javascript", marker)
        _expect("no-store" in response.header("cache-control").lower(),
                f"{path}: stale public JavaScript must not be cached")

    for path in PRIVATE_PATHS:
        response = get(path)
        _expect(response.status == 401,
                f"{path}: private route expected HTTP 401, got {response.status}",
                retryable=response.status in (502, 503, 504))
        _expect(response.header("www-authenticate").lower().startswith("basic "),
                f"{path}: missing HTTP Basic auth challenge")
        _expect("no-store" in response.header("cache-control").lower(),
                f"{path}: unauthorized content must not be cached")
        _expect(response.header("x-content-type-options") == "nosniff",
                f"{path}: missing nosniff")

    # Never issue a POST or authenticated request as part of this gate.
    _expect(all(method == "GET" for method, _, _ in observed),
            "Release probe attempted a non-read-only request")
    return observed


def wait_for_release(base, expected_sha, fetch=request_once, *,
                     attempts=30, delay=8.0, timeout=10.0, sleep=time.sleep, emit=print):
    if attempts < 1 or delay < 0 or timeout <= 0:
        raise ValueError("Invalid release retry settings")
    validate_base_url(base)
    if not valid_sha(expected_sha):
        raise ValueError("Full expected commit SHA required")
    for attempt in range(1, attempts + 1):
        try:
            result = verify_once(base, expected_sha, fetch=fetch, timeout=timeout)
            emit(f"PASS: deployed {expected_sha.lower()} | {len(result)} anonymous GET checks | "
                 "public access and private auth enforced | PayPal untouched")
            return result
        except ProbeFailure as exc:
            if not exc.retryable or attempt == attempts:
                raise
            emit(f"Release not yet ready ({attempt}/{attempts}): {exc}")
            sleep(delay)
    raise AssertionError("unreachable")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_ORIGIN)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--attempts", type=int, default=30)
    parser.add_argument("--delay", type=float, default=8)
    parser.add_argument("--timeout", type=float, default=10)
    args = parser.parse_args(argv)
    try:
        wait_for_release(args.base_url, args.expected_sha,
                         attempts=args.attempts, delay=args.delay,
                         timeout=args.timeout)
    except (ProbeFailure, ValueError) as exc:
        print(f"FAIL: CircleSplit public release gate: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
