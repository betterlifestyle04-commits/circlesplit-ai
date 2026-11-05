"""Offline regression checks for hosted Gemini and PayPal request budgets."""
import importlib

import pytest
from fastapi.testclient import TestClient

from provider_limits import ProviderLimiter, provider_group


OWNER = ("owner", "owner-very-long-demo-password")
JUDGE = ("evaluator", "judge-long-distinct-password")
EVENT = {"name": "No provider charges", "date": "2026-11-09", "note": "fictional"}


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "rate-limits.sqlite3"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.setenv("DEMO_USERNAME", "owner")
    monkeypatch.setenv("DEMO_PASSWORD", OWNER[1])
    monkeypatch.setenv("JUDGE_ACCESS_ENABLED", "1")
    monkeypatch.setenv("JUDGE_USERNAME", JUDGE[0])
    monkeypatch.setenv("JUDGE_PASSWORD", JUDGE[1])
    monkeypatch.setenv("JUDGE_ACCESS_EXPIRES_AT", "2099-01-01T00:00:00Z")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def test_provider_route_classification_is_exact():
    assert provider_group("POST", "/api/ai/parse") == "ai"
    assert provider_group("POST", "/api/ai/plan/18") == "ai"
    assert provider_group("POST", "/api/paypal/orders/12/8") == "checkout"
    assert provider_group("POST", "/api/paypal/capture") == "reconciliation"
    assert provider_group("POST", "/api/paypal/order-status/ABC-123") == "reconciliation"
    for method, path in [
        ("GET", "/api/ai/parse"),
        ("POST", "/api/paypal/webhook"),
        ("POST", "/api/ai/parse/not-really"),
        ("POST", "/api/paypal/orders/7/8/extra"),
        ("POST", "/api/ai/plan/../parse"),
        ("POST", "/api/events"),
        ("POST", "/api/paypal/order-status/<unknown>"),
    ]:
        assert provider_group(method, path) is None


def test_ai_shared_judge_budget_and_owner_isolation(client):
    endpoint = "/api/ai/parse"
    for remaining in range(11, -1, -1):
        r = client.post(endpoint, auth=JUDGE, json={"note": "Example expenses totaling $12"})
        assert r.status_code == 503  # Credentials intentionally absent.
        assert r.headers["X-RateLimit-Limit"] == "12"
        assert r.headers["X-RateLimit-Remaining"] == str(remaining)
    denied = client.post(endpoint, auth=JUDGE, json={"note": "No actual provider call"})
    assert denied.status_code == 429
    assert denied.headers["Retry-After"] == "60" or 1 <= int(denied.headers["Retry-After"]) <= 60
    assert denied.json()["detail"] == "Too many sandbox provider requests. Retry later."
    assert client.post(endpoint, auth=OWNER, json={"note": "Independent owner budget"}).status_code == 503
    assert client.post("/api/events", auth=JUDGE, json=EVENT).status_code == 200


def test_orders_and_reconciliation_budgets_are_separate(client):
    # Only owner credentials may reach PayPal Sandbox action budgets.
    for i in range(6):
        r = client.post("/api/paypal/orders/1/999", auth=OWNER)
        assert r.status_code == 503
        assert r.headers["X-RateLimit-Remaining"] == str(5 - i)
    assert client.post("/api/paypal/orders/1/999", auth=OWNER).status_code == 429
    # A blocked judge request never consumes either owner or judge provider quotas.
    judge = client.post("/api/paypal/orders/1/999", auth=JUDGE)
    assert judge.status_code == 403
    assert "X-RateLimit-Limit" not in judge.headers
    # Read-only recovery is still accessible to the judge.
    assert client.get("/api/paypal/recovery", auth=JUDGE).status_code == 200
    assert client.post("/api/paypal/capture", auth=JUDGE,
                       json={"order_id": "UNRECOGNIZED"}).status_code == 403
    assert client.post("/api/paypal/capture", auth=OWNER,
                       json={"order_id": "UNRECOGNIZED"}).status_code == 404
    assert client.post("/api/ai/parse", auth=JUDGE, json={"note": "Completely separate bucket"}).status_code == 503


def test_unauthorized_or_cross_origin_requests_never_consume_provider_budget(client):
    endpoint = "/api/ai/parse"
    for _ in range(15):
        assert client.post(endpoint, json={"note": "not authorized"}).status_code == 401
        assert client.post(endpoint, auth=JUDGE, headers={
            "Origin": "https://malicious.example", "Sec-Fetch-Site": "cross-site"
        }, json={"note": "cross origin"}).status_code == 403
    allowed = client.post(endpoint, auth=JUDGE, json={"note": "Legitimate test"})
    assert allowed.status_code == 503
    assert allowed.headers["X-RateLimit-Remaining"] == "11"


def test_webhook_and_local_mode_not_throttled(client, monkeypatch, tmp_path):
    for _ in range(7):
        # Webhook is signed independently; missing webhook secret always fails closed.
        assert client.post("/api/paypal/webhook", json={"id": "not-signed"},
            headers={"Origin": "https://outside.example",
                     "Sec-Fetch-Site": "cross-site"}).status_code == 503
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as local:
        for _ in range(14):
            r = local.post("/api/ai/parse", json={"note": "Only local testing"})
            assert r.status_code == 503
            assert "X-RateLimit-Limit" not in r.headers


def test_sliding_window_recovers_and_does_not_consume_blocked_attempts():
    tick = [100.0]
    limiter = ProviderLimiter(clock=lambda: tick[0])
    for n in range(12):
        assert limiter.attempt("judge", "ai") == (True, 11 - n, 0, 12)
    assert limiter.attempt("judge", "ai") == (False, 0, 60, 12)
    tick[0] = 159.8
    assert limiter.attempt("judge", "ai") == (False, 0, 1, 12)
    tick[0] = 160
    assert limiter.attempt("judge", "ai") == (True, 11, 0, 12)
    assert limiter.attempt("owner", "ai") == (True, 11, 0, 12)
