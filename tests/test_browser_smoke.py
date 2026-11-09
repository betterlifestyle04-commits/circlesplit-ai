"""No-network regression tests for the hosted Chromium release guard.

A mocked /health response cannot impersonate a completed PayPal capture.
These tests verify only request allowlisting and exact source identification.
"""
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import browser_smoke
from verify_live import DEFAULT_ORIGIN, Result


SHA = "a" * 40


@pytest.mark.parametrize("path", sorted(browser_smoke.PUBLIC_BROWSER_PATHS))
def test_hosted_chromium_allows_only_explicit_public_static_gets(path):
    assert browser_smoke.permitted_browser_request(
        DEFAULT_ORIGIN, DEFAULT_ORIGIN + path, "GET", hosted=True
    )


@pytest.mark.parametrize(("url", "method"), [
    (DEFAULT_ORIGIN + "/api/state", "GET"),
    (DEFAULT_ORIGIN + "/api/paypal/capture", "POST"),
    (DEFAULT_ORIGIN + "/workspace", "GET"),
    (DEFAULT_ORIGIN + "/static/index.html", "GET"),
    (DEFAULT_ORIGIN + "/static/insights.js", "GET"),
    (DEFAULT_ORIGIN + "/judge?token=possible-leak", "GET"),
    (DEFAULT_ORIGIN + "/judge#private", "GET"),
    (DEFAULT_ORIGIN + "/judge", "POST"),
    (DEFAULT_ORIGIN + "/judge", "PUT"),
    (DEFAULT_ORIGIN + "/judge", "HEAD"),
    ("https://evil.example/judge", "GET"),
    ("http://circlesplit-ai-demo.onrender.com/judge", "GET"),
    ("https://circlesplit-ai-demo.onrender.com:8443/judge", "GET"),
    ("https://someone:secret@circlesplit-ai-demo.onrender.com/judge", "GET"),
    ("https://circlesplit-ai-demo.onrender.com.evil.example/judge", "GET"),
    ("file:///etc/passwd", "GET"),
])
def test_hosted_chromium_rejects_mutation_private_api_and_off_origin(url, method):
    assert not browser_smoke.permitted_browser_request(
        DEFAULT_ORIGIN, url, method, hosted=True
    )


def test_local_chromium_rejects_external_network_and_all_api_calls():
    base = "http://127.0.0.1:8181"
    assert browser_smoke.permitted_browser_request(base, base + "/judge", "GET")
    assert not browser_smoke.permitted_browser_request(base, base + "/api/state", "GET")
    assert not browser_smoke.permitted_browser_request(base, base + "/judge", "POST")
    assert not browser_smoke.permitted_browser_request(
        base, "http://127.0.0.1:8182/", "GET"
    )
    assert not browser_smoke.permitted_browser_request(
        base, "http://localhost:8181/", "GET"
    )


def valid_health():
    return {
        "status": "ok",
        "mode": "sandbox-only",
        "git_commit": SHA,
    }


def test_live_source_guard_uses_fixed_origin_and_anonymous_get():
    calls = []
    def fetch(url, method, timeout):
        calls.append((url, method, timeout))
        return Result(200, {}, json.dumps(valid_health()).encode())
    browser_smoke.verify_hosted_revision(SHA, fetch=fetch)
    assert calls == [(DEFAULT_ORIGIN + "/health", "GET", 12.0)]
    assert urlsplit(calls[0][0]).hostname == "circlesplit-ai-demo.onrender.com"


@pytest.mark.parametrize("payload", [
    {**valid_health(), "git_commit": "b" * 40},
    {**valid_health(), "git_commit": None},
    {**valid_health(), "status": "unhealthy"},
    {**valid_health(), "mode": "production"},
    [],
    {"status": "ok"},
])
def test_live_source_guard_fails_closed_on_invalid_or_stale_health(payload):
    def fetch(_url, method, timeout):
        return Result(200, {}, json.dumps(payload).encode())
    with pytest.raises((AssertionError, ValueError)):
        browser_smoke.verify_hosted_revision(SHA, fetch=fetch)


@pytest.mark.parametrize("body,status", [
    (b"{invalid", 200),
    (b"{}", 503),
    (b"<html>redirect</html>", 302),
])
def test_live_source_guard_fails_closed_on_non_json_status_or_redirect(body,status):
    def fetch(_url, method, timeout):
        return Result(status, {}, body)
    with pytest.raises(AssertionError):
        browser_smoke.verify_hosted_revision(SHA, fetch=fetch)


@pytest.mark.parametrize("sha", ["", "a" * 39, "a" * 41, "xyz", None, 12])
def test_live_browser_requires_full_git_revision_before_network(sha):
    def fail_if_called(*args, **kwargs):
        raise AssertionError("Invalid SHA must be rejected before network")
    with pytest.raises(ValueError):
        browser_smoke.verify_hosted_revision(sha, fetch=fail_if_called)


def test_cli_rejects_hosted_mode_without_sha_before_browser_or_network():
    with pytest.raises(SystemExit) as failed:
        browser_smoke.main(["--hosted-read-only"])
    assert failed.value.code == 2
    with pytest.raises(SystemExit) as failed:
        browser_smoke.main(["--expected-sha", SHA])
    assert failed.value.code == 2
