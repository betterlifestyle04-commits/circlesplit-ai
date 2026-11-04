"""Participant approval withdrawal: private-link authority, not real identities.

All payments are mocked and remain PayPal SANDBOX only.
"""
import importlib

import pytest
from fastapi.testclient import TestClient
import paypal


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "withdrawal.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as t:
        yield t


def participant(client):
    event = client.get("/api/state").json()["events"][0]
    person = event["people"][0]
    eid, pid = event["id"], person["id"]
    link = client.post(f"/api/events/{eid}/people/{pid}/invite")
    assert link.status_code == 200
    bearer = {"Authorization": "Bearer " + link.json()["token"]}
    return eid, pid, bearer


def overview(client, bearer):
    response = client.get("/api/participant/overview", headers=bearer)
    assert response.status_code == 200, response.text
    return response.json()


def history_count(client, eid):
    d = client.get(f"/api/events/{eid}/history").json()
    return sum(e["action"] == "participant_approval_withdrawn" for e in d["entries"])


def test_withdrawal_clears_approval_stays_private_and_is_idempotent(client):
    eid, pid, bearer = participant(client)
    assert client.post("/api/participant/approve", headers=bearer).status_code == 200
    old = overview(client,bearer)
    assert old["approved"] is True and old["approval_withdrawn"] is False
    assert old["checkout_started"] is False
    res = client.post("/api/participant/withdraw", headers=bearer)
    assert res.status_code == 200, res.text
    assert res.json() == {
        "ok": True,"already_withdrawn":False,
        "payment_changed":False,"approval_withdrawn":True
    }
    assert "no-store" in res.headers["Cache-Control"]
    d = overview(client,bearer)
    assert d["approved"] is False and d["approval_withdrawn"] is True
    assert d["status"] == "unpaid"
    assert d["checkout_started"] is False
    assert history_count(client,eid) == 1
    repeat=client.post("/api/participant/withdraw", headers=bearer)
    assert repeat.status_code == 200
    assert repeat.json()["already_withdrawn"] is True
    assert history_count(client,eid) == 1
    assert client.get("/api/state").json()["events"][0]["sandbox_cents"] == 0
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 409
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code == 409


def test_withdrawal_can_reject_organizer_approval_before_any_approval(client):
    eid,pid,bearer = participant(client)
    assert overview(client,bearer)["approved"] is False
    assert client.post("/api/participant/withdraw",headers=bearer).status_code == 200
    block=client.post(f"/api/events/{eid}/people/{pid}/approve")
    assert block.status_code == 409
    assert "withdrew approval" in block.json()["detail"]
    assert overview(client,bearer)["approval_withdrawn"] is True


def test_new_private_link_approval_can_restore_consent(client, monkeypatch):
    eid,pid,bearer = participant(client)
    client.post("/api/participant/withdraw",headers=bearer)
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 409
    new=client.post("/api/participant/approve",headers=bearer)
    assert new.status_code == 200,new.text
    d=overview(client,bearer)
    assert d["approved"] is True and d["approval_withdrawn"] is False
    assert d["approval_source"] == "participant_link"
    monkeypatch.setattr(paypal, "configured", lambda: True)
    async def fake_order(*args):
        return {"id":"TEST-CONSENT-RESTORED-ORDER",
                "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"}
    monkeypatch.setattr(paypal, "order", fake_order)
    checkout=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert checkout.status_code == 200,checkout.text
    assert overview(client,bearer)["checkout_started"] is True


def test_withdrawal_stays_blocked_after_budget_recalculation(client):
    eid,pid,bearer=participant(client)
    assert client.post("/api/participant/withdraw",headers=bearer).status_code == 200
    assert client.post(f"/api/events/{eid}/expenses",json={
        "title":"Extra water","amount":"20.00","category":"food"
    }).status_code == 200
    # Changing the budget revokes the old link, but must not erase opt-out.
    assert client.get("/api/participant/overview",headers=bearer).status_code == 404
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 409
    new=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    latest={"Authorization":"Bearer "+new}
    d=overview(client,latest)
    assert d["approval_withdrawn"] is True and d["approved"] is False
    assert client.post("/api/participant/approve",headers=latest).status_code == 200
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 200


def test_rsvp_changes_do_not_reset_withdrawal(client):
    eid,pid,bearer=participant(client)
    assert client.post("/api/participant/withdraw",headers=bearer).status_code == 200
    declined=client.post("/api/participant/rsvp",headers=bearer,json={"status":"declined"})
    going=client.post("/api/participant/rsvp",headers=bearer,json={"status":"going"})
    assert declined.status_code == going.status_code == 200
    assert overview(client,bearer)["approval_withdrawn"] is True
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 409


def test_withdrawal_is_forbidden_after_checkout_started(client, monkeypatch):
    eid,pid,bearer=participant(client)
    assert client.post("/api/participant/approve",headers=bearer).status_code == 200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    async def fake_order(*args):
        return {"id":"TEST-WITHDRAW-LOCKED-ORDER",
                "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=FAKE"}
    monkeypatch.setattr(paypal,"order",fake_order)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code == 200
    denied=client.post("/api/participant/withdraw",headers=bearer)
    assert denied.status_code == 409
    assert "already started" in denied.json()["detail"]
    assert overview(client,bearer)["checkout_started"] is True
    assert overview(client,bearer)["approved"] is True
    assert history_count(client,eid) == 0
    state=client.get("/api/paypal/recovery").json()
    assert state["summary"]["created"] == 1


def test_hosted_withdrawal_is_capability_gated_and_no_store(client, monkeypatch):
    eid,pid,bearer=participant(client)
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","unique-long-sandbox-owner-password")
    assert client.post("/api/participant/withdraw").status_code == 401
    assert client.post("/api/participant/withdraw",headers={
        "Authorization":"Bearer invalid"
    }).status_code == 401
    accepted=client.post("/api/participant/withdraw",headers=bearer)
    assert accepted.status_code == 200,accepted.text
    assert "no-store" in accepted.headers["Cache-Control"]
    assert client.post("/api/events/1/people/1/approve",headers=bearer).status_code == 401
    # A browser from another origin must not mutate even when it holds a token.
    denied=client.post("/api/participant/withdraw",headers={
        **bearer,"Origin":"https://malicious.example","Sec-Fetch-Site":"cross-site"
    })
    assert denied.status_code == 403


def test_invalid_revoked_link_cannot_withdraw(client):
    eid,pid,bearer=participant(client)
    assert client.post(f"/api/events/{eid}/people/{pid}/invite/revoke").status_code == 200
    assert client.post("/api/participant/withdraw",headers=bearer).status_code == 404


def test_withdrawal_schema_migrates_legacy_database(client):
    import app
    with app.db() as c:
        columns={row["name"] for row in c.execute("PRAGMA table_info(people)")}
        assert "approval_withdrawn_at" in columns
        assert c.execute(
            "SELECT approval_withdrawn_at FROM people LIMIT 1"
        ).fetchone()[0] is None
