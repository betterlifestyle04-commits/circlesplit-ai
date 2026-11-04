"""Hosted demo browser hardening. Entirely offline, with no real payments."""
import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def hosted_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "security.sqlite3"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.setenv("DEMO_USERNAME", "judge")
    monkeypatch.setenv("DEMO_PASSWORD", "an-unpredictable-test-password")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://circlesplit-ai-demo.onrender.com")
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as client:
        yield client


AUTH = ("judge", "an-unpredictable-test-password")
PAYLOAD = {"name": "Security test meetup", "date": "2026-11-09", "note": "fictional"}


@pytest.mark.parametrize("headers", [
    {"Origin": "https://attacker.example"},
    {"Origin": "null"},
    {"Origin": "http://circlesplit-ai-demo.onrender.com"},
    {"Origin": "https://circlesplit-ai-demo.onrender.com.evil.example"},
    {"Origin": "https://circlesplit-ai-demo.onrender.com/path"},
    {"Sec-Fetch-Site": "cross-site"},
    {"Sec-Fetch-Site": "same-site", "Origin": "https://circlesplit-ai-demo.onrender.com"},
    {"Sec-Fetch-Site": "cross-site", "Origin": "https://circlesplit-ai-demo.onrender.com"},
])
def test_hosted_mutations_refuse_untrusted_browser_context(hosted_client, headers):
    before = len(hosted_client.get("/api/state", auth=AUTH).json()["events"])
    r = hosted_client.post("/api/events", auth=AUTH, json=PAYLOAD, headers=headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "Cross-origin modification blocked"
    after = len(hosted_client.get("/api/state", auth=AUTH).json()["events"])
    assert after == before


@pytest.mark.parametrize("headers", [
    {"Origin": "https://circlesplit-ai-demo.onrender.com", "Sec-Fetch-Site": "same-origin"},
    {"Origin": "https://circlesplit-ai-demo.onrender.com:443"},
    {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"},
    {},
])
def test_hosted_mutations_accept_same_origin_or_authenticated_script(hosted_client, headers):
    r = hosted_client.post("/api/events", auth=AUTH, json=PAYLOAD, headers=headers)
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["id"], int)


def test_get_and_paypal_webhook_remain_accessible_without_browser_origin(hosted_client):
    assert hosted_client.get("/api/state", auth=AUTH, headers={
        "Origin": "https://somewhere.example", "Sec-Fetch-Site": "cross-site"
    }).status_code == 200
    # The independently signed PayPal webhook bypasses the browser-origin check
    # but still fails closed before verification if webhook ID is missing.
    r = hosted_client.post("/api/paypal/webhook", json={"id": "WH-1"}, headers={
        "Origin": "https://api-m.sandbox.paypal.com", "Sec-Fetch-Site": "cross-site"
    })
    assert r.status_code == 503


def test_security_headers_cover_public_and_protected_responses(hosted_client):
    responses = [
        hosted_client.get("/"),
        hosted_client.get("/workspace"),
        hosted_client.get("/workspace", auth=AUTH),
        hosted_client.get("/api/state", auth=AUTH),
        hosted_client.post("/api/events", auth=AUTH, json=PAYLOAD,
                           headers={"Origin": "https://evil.example"}),
        hosted_client.get("/participant"),
        hosted_client.get("/api/participant/overview"),
    ]
    assert [r.status_code for r in responses] == [200, 401, 200, 200, 403, 200, 401]
    for r in responses:
        assert r.headers["x-content-type-options"] == "nosniff"
        assert r.headers["x-frame-options"] == "DENY"
        assert r.headers["referrer-policy"] == "no-referrer"
        assert "geolocation=()" in r.headers["permissions-policy"]
    for r in responses[1:]:
        assert "no-store" in r.headers["cache-control"]


def test_local_trust_mode_keeps_existing_development_behavior(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "local.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as client:
        result = client.post("/api/events", json=PAYLOAD,
            headers={"Origin": "https://somewhere.example", "Sec-Fetch-Site": "cross-site"})
        assert result.status_code == 200
