"""Anonymous, no-secrets live-release gate contract and in-process integration tests.

All positive access checks run against FastAPI TestClient with fake hosted
credentials; no external requests, provider calls, or payments occur.
"""
from dataclasses import replace
import importlib
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from security import PUBLIC_DEMO_SCRIPT_PATHS
from tools.verify_live import (
    DEFAULT_ORIGIN,
    PRIVATE_PATHS,
    PUBLIC_PAGES,
    PUBLIC_SCRIPTS,
    ProbeFailure,
    Result,
    valid_sha,
    validate_base_url,
    verify_once,
    wait_for_release,
)

SHA = "a" * 40


@pytest.fixture
def hosted(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "release-gate.sqlite"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.setenv("DEMO_USERNAME", "owner")
    monkeypatch.setenv("DEMO_PASSWORD", "private-test-only-demo-password")
    monkeypatch.setenv("RENDER_GIT_COMMIT", SHA)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as client:
        yield client


def transport(client, *, rewrite=None):
    history = []

    def get(url, method, timeout):
        assert url.startswith("https://demo.example/")
        assert method in ("GET", "HEAD")
        assert timeout > 0
        path = urlsplit(url).path
        history.append((method, path))
        response = client.request(method, path, follow_redirects=False)
        result = Result(
            response.status_code,
            {key.lower(): value for key, value in response.headers.items()},
            response.content,
        )
        if rewrite is not None:
            return rewrite(path, result)
        return result

    return get, history


def failure(test, pattern=None, retryable=None):
    with pytest.raises(ProbeFailure, match=pattern) as info:
        test()
    if retryable is not None:
        assert info.value.retryable is retryable


def test_all_public_js_assets_match_hosted_exact_allowlist():
    assert set(PUBLIC_SCRIPTS) == PUBLIC_DEMO_SCRIPT_PATHS
    assert len(PUBLIC_SCRIPTS) == 4
    assert len(PRIVATE_PATHS) >= 7
    assert not set(PRIVATE_PATHS) & set(PUBLIC_SCRIPTS)
    assert "/api/paypal/webhook" not in PRIVATE_PATHS
    assert "/api/paypal/capture" not in PRIVATE_PATHS  # no POST payment probe
    assert all(not path.startswith("/api/") for path in PUBLIC_SCRIPTS)


def test_release_gate_fully_checks_actual_hosted_app_without_credentials(hosted, monkeypatch):
    import paypal
    async def forbidden(*_args, **_kwargs):
        raise AssertionError("Release inspection must never call PayPal Sandbox")
    monkeypatch.setattr(paypal, "details", forbidden)
    monkeypatch.setattr(paypal, "capture", forbidden)
    monkeypatch.setattr(paypal, "order", forbidden)
    fetch, calls = transport(hosted)
    result = verify_once("https://demo.example", SHA, fetch=fetch)
    expected = ["/health", *PUBLIC_PAGES, *PUBLIC_SCRIPTS, *PRIVATE_PATHS]
    assert [path for _, path, _ in result] == expected
    assert all(status in (200, 401) for _, _, status in result)
    assert [path for _, path in calls] == expected
    assert all(method == "GET" for method, _ in calls)
    # Actual app state isn't read or modified in an authenticated context.
    assert not any(path.startswith("/api/paypal/orders/") for _, path in calls)


def test_wrong_sha_is_explicitly_stale_and_does_not_access_other_endpoints(hosted):
    fetch, calls = transport(hosted)
    failure(lambda: verify_once("https://demo.example", "b" * 40, fetch=fetch),
            "differs from expected", retryable=True)
    assert calls == [("GET", "/health")]


def test_missing_commit_is_not_assumed_current(hosted):
    fetch, calls = transport(hosted, rewrite=lambda path, response:
        replace(response, body=response.body.replace(SHA.encode(), b"null"))
        if path == "/health" else response)
    # Replacing a JSON string with null yields invalid JSON if quotes persist;
    # either way the deployment must never be marked ready.
    failure(lambda: verify_once("https://demo.example", SHA, fetch=fetch),
            retryable=False)
    assert calls == [("GET", "/health")]


@pytest.mark.parametrize("path", [
    "/static/public_recovery.js",
    "/static/public_portability.js",
    "/static/public_scenarios.js",
    "/static/judge_walkthrough.js",
    "/",
    "/judge",
])
def test_missing_public_assets_or_pages_fail_release(hosted, path):
    fetch, calls = transport(hosted, rewrite=lambda p, r:
        replace(r, status=404, body=b"") if p == path else r)
    failure(lambda: verify_once("https://demo.example", SHA, fetch=fetch),
            "expected public HTTP 200", retryable=False)
    assert any(p == path for _, p in calls)


@pytest.mark.parametrize("path", [
    "/workspace",
    "/api/state",
    "/api/paypal/recovery",
    "/api/paypal/webhook-audit",
    "/api/paypal/reconciliation-export",
    "/static/index.html",
    "/static/participant.html",
    "/static/insights.js",
])
def test_accidental_anonymous_access_to_private_path_fails_gate(hosted, path):
    fetch, calls = transport(hosted, rewrite=lambda p, r:
        replace(r, status=200) if p == path else r)
    failure(lambda: verify_once("https://demo.example", SHA, fetch=fetch),
            "private route expected HTTP 401", retryable=False)
    assert any(p == path for _, p in calls)


@pytest.mark.parametrize("path", [
    "/health",
    "/static/public_scenarios.js",
    "/workspace",
    "/api/state",
])
def test_unsafe_cache_headers_block_release_for_sensitive_responses(hosted, path):
    fetch, _ = transport(hosted, rewrite=lambda p, r:
        replace(r, headers={**r.headers, "cache-control": "max-age=600"})
        if p == path else r)
    failure(lambda: verify_once("https://demo.example", SHA, fetch=fetch),
            "not be cached|must not be cached|stale public JavaScript")


def test_broken_java_script_content_type_fails_closed(hosted):
    fetch, _ = transport(hosted, rewrite=lambda p, r:
        replace(r, headers={**r.headers, "content-type": "text/html"})
        if p == "/static/public_portability.js" else r)
    failure(lambda: verify_once("https://demo.example", SHA, fetch=fetch),
            "JavaScript Content-Type")


def test_missing_release_marker_fails_even_if_server_says_200(hosted):
    fetch, _ = transport(hosted, rewrite=lambda p, r:
        replace(r, body=b"nothing to do with CircleSplit")
        if p == "/judge" else r)
    failure(lambda: verify_once("https://demo.example", SHA, fetch=fetch),
            "marker absent")


def test_stale_revision_retries_then_accepts_full_correct_public_inspection(hosted):
    count = 0
    fetch, calls = transport(hosted)
    messages = []
    pauses = []
    def intermittent(url, method, timeout):
        nonlocal count
        result = fetch(url, method, timeout)
        if url.endswith("/health"):
            count += 1
            if count <= 2:
                return replace(result, body=result.body.replace(SHA.encode(), ("b"*40).encode()))
        return result
    output = wait_for_release("https://demo.example", SHA, fetch=intermittent,
                              attempts=4, delay=0.1, sleep=pauses.append,
                              emit=messages.append)
    assert count == 3
    assert pauses == [0.1, 0.1]
    assert len(output) == 1 + len(PUBLIC_PAGES) + len(PUBLIC_SCRIPTS) + len(PRIVATE_PATHS)
    assert len([path for _, path in calls if path == "/health"]) == 3
    assert messages[-1].startswith("PASS: deployed " + SHA)


def test_transient_503_can_retry_but_permanent_security_error_cannot(hosted):
    fetch, _ = transport(hosted)
    attempts = []
    def unavailable(url, method, timeout):
        attempts.append(url)
        result = fetch(url, method, timeout)
        return replace(result, status=503) if url.endswith("/health") else result
    failure(lambda: wait_for_release("https://demo.example", SHA, fetch=unavailable,
                                    attempts=3, delay=0, sleep=lambda _: None,
                                    emit=lambda _: None),
            "/health: HTTP 503", retryable=True)
    assert len(attempts) == 3

    attempts.clear()
    def accidentally_public(url, method, timeout):
        attempts.append(url)
        result = fetch(url, method, timeout)
        return replace(result, status=200) if url.endswith("/workspace") else result
    failure(lambda: wait_for_release("https://demo.example", SHA, fetch=accidentally_public,
                                    attempts=10, delay=0, sleep=lambda _: None,
                                    emit=lambda _: None),
            "private route expected HTTP 401", retryable=False)
    assert len(attempts) == 1 + len(PUBLIC_PAGES) + len(PUBLIC_SCRIPTS) + 1


@pytest.mark.parametrize("origin", [
    "http://demo.example", "https://user:secret@demo.example",
    "https://demo.example/private", "https://demo.example?x=1",
    "https://demo.example/#top", " https://demo.example",
    "file:///tmp/service", "//demo.example", "https://demo.example:invalid",
    "", None
])
def test_only_bare_https_origins_are_accepted(origin):
    with pytest.raises(ValueError):
        validate_base_url(origin)


@pytest.mark.parametrize("sha", ["", "a" * 39, "g" * 40, "main", None, "a" * 41])
def test_sha_must_be_full_hex(sha):
    assert not valid_sha(sha)


def test_wait_rejects_invalid_argument_before_any_http():
    calls = []
    def fetch(*args):
        calls.append(args)
        raise AssertionError("Must not call external services")
    for invalid in [None, "abc", "f" * 41]:
        with pytest.raises(ValueError):
            wait_for_release(DEFAULT_ORIGIN, invalid, fetch=fetch)
    with pytest.raises(ValueError):
        wait_for_release("http://insecure.example", SHA, fetch=fetch)
    with pytest.raises(ValueError):
        wait_for_release(DEFAULT_ORIGIN, SHA, attempts=0, fetch=fetch)
    assert calls == []
