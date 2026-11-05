"""Safe, read-only preflight for a NEW PayPal Sandbox order.

The checks do not call PayPal; a successful preflight does not authorize or
guarantee actual checkout. All provider actions here are test doubles.
"""
import importlib
import pytest
from fastapi.testclient import TestClient
import paypal


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "preflight.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as app_client:
        yield app_client


def first_person(client):
    e = client.get("/api/state").json()["events"][0]
    return e["id"], e["people"][0]["id"], e["people"][0]["share_cents"]


def get_preflight(client, eid, pid):
    return client.get(f"/api/paypal/checkout-readiness/{eid}/{pid}")


def codes(report):
    return {item["code"] for item in report["blockers"]}


def mock_provider(monkeypatch):
    monkeypatch.setattr(paypal, "configured", lambda: True)
    async def never_provider(*args, **kwargs):
        raise AssertionError("Preflight must not call any provider")
    monkeypatch.setattr(paypal, "details", never_provider)
    monkeypatch.setattr(paypal, "capture", never_provider)
    monkeypatch.setattr(paypal, "order", never_provider)


def test_preflight_discloses_clear_blockers_without_changes_or_provider_calls(client, monkeypatch):
    eid, pid, amount = first_person(client)
    mock_provider(monkeypatch)
    import app
    with app.db() as conn:
        before = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
        history = conn.execute("SELECT COUNT(*) FROM event_history").fetchone()[0]
    result = get_preflight(client, eid, pid)
    assert result.status_code == 200, result.text
    assert "no-store" in result.headers["Cache-Control"]
    data = result.json()
    assert data["mode"] == "PAYPAL_SANDBOX"
    assert data["can_create_order"] is False
    assert data["amount_cents"] == amount
    assert "approval_required" in codes(data)
    assert all(set(item) == {"code", "explanation"} for item in data["blockers"])
    assert "order_id" not in str(data)
    with app.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == before
        assert conn.execute("SELECT COUNT(*) FROM event_history").fetchone()[0] == history


def test_approved_share_passes_preflight_and_creates_only_one_order(client, monkeypatch):
    import app
    eid, pid, amount = first_person(client)
    mock_provider(monkeypatch)
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 200
    eligible = get_preflight(client, eid, pid).json()
    assert eligible["can_create_order"] is True, eligible
    assert eligible["blockers"] == []
    assert eligible["amount_cents"] == amount

    calls = []
    async def test_order(amount_cents, event_id, person_id, return_url, key):
        calls.append((amount_cents, event_id, person_id))
        return {"id": "TEST-CHECKOUT-ORDER-123",
                "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=TEST"}
    monkeypatch.setattr(paypal, "order", test_order)
    created = client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert created.status_code == 200, created.text
    assert calls == [(amount, eid, pid)]
    locked = get_preflight(client, eid, pid).json()
    assert locked["can_create_order"] is False
    assert "existing_order" in codes(locked)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code == 409
    assert calls == [(amount, eid, pid)]
    with app.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM payments WHERE person_id=?", (pid,)).fetchone()[0] == 1


def test_corrupted_event_budget_blocks_new_order_even_with_valid_approval(client, monkeypatch):
    import app
    eid, pid, amount = first_person(client)
    mock_provider(monkeypatch)
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 200
    with app.db() as conn:
        other = conn.execute(
            "SELECT id FROM people WHERE event_id=? AND id!=? LIMIT 1", (eid, pid)
        ).fetchone()
        assert other
        conn.execute("UPDATE people SET share_cents=share_cents+7 WHERE id=?", (other["id"],))
    report = get_preflight(client, eid, pid).json()
    assert report["can_create_order"] is False
    assert "allocation_inconsistent" in codes(report)
    denied = client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert denied.status_code == 409
    assert "exact-cent" in denied.json()["detail"]
    assert get_preflight(client, eid, pid).json()["amount_cents"] == amount
    with app.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 0


def test_rsvp_decline_and_withdrawn_approval_have_safe_explanations(client, monkeypatch):
    eid, pid, _ = first_person(client)
    mock_provider(monkeypatch)
    token = client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    bearer = {"Authorization": "Bearer " + token}
    assert client.post("/api/participant/rsvp", headers=bearer,
                       json={"status": "declined"}).status_code == 200
    d = get_preflight(client, eid, pid).json()
    assert "attendance_declined" in codes(d)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code == 409
    assert client.post("/api/participant/rsvp", headers=bearer,
                       json={"status": "going"}).status_code == 200
    assert client.post("/api/participant/withdraw", headers=bearer).status_code == 200
    blocked = get_preflight(client, eid, pid).json()
    assert "approval_required" in codes(blocked)
    assert blocked["can_create_order"] is False


def test_unconfigured_sandbox_and_opt_in_storage_gate_block_readiness(client, monkeypatch):
    import app
    eid, pid, _ = first_person(client)
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 200
    no_creds = get_preflight(client, eid, pid).json()
    assert no_creds["can_create_order"] is False
    assert "sandbox_not_configured" in codes(no_creds)
    mock_provider(monkeypatch)
    monkeypatch.setenv("CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB", "1")
    gate = get_preflight(client, eid, pid).json()
    assert gate["can_create_order"] is False
    assert "durable_storage_required" in codes(gate)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code == 503
    with app.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == 0


def test_preflight_fails_for_wrong_event_or_missing_participant(client, monkeypatch):
    mock_provider(monkeypatch)
    eid, pid, _ = first_person(client)
    assert get_preflight(client, eid, 999999).status_code == 404
    assert get_preflight(client, 999999, pid).status_code == 404
    assert get_preflight(client, -1, pid).status_code == 404


def test_preflight_is_hosted_organizer_only_and_no_private_invitee_access(client, monkeypatch):
    eid, pid, _ = first_person(client)
    mock_provider(monkeypatch)
    bearer = client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.setenv("DEMO_PASSWORD", "secret-owner-or-judge-password")
    url = f"/api/paypal/checkout-readiness/{eid}/{pid}"
    assert client.get(url).status_code == 401
    assert client.get(url, headers={"Authorization": "Bearer " + bearer}).status_code == 401
    response = client.get(url, auth=("judge", "secret-owner-or-judge-password"))
    assert response.status_code == 200
    assert "no-store" in response.headers["Cache-Control"]
