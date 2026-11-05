"""Offline payment-ledger invariants; all provider responses are mocked.

These tests do NOT process real money or prove current sandbox availability.
"""
import importlib
import sqlite3

import pytest
from fastapi.testclient import TestClient
import paypal


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "captures.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as app_client:
        yield app_client


def first_event(client):
    return client.get("/api/state").json()["events"][0]


def mock_orders(monkeypatch):
    monkeypatch.setattr(paypal, "configured", lambda: True)

    async def create(amount, eid, pid, url, key):
        return {"id": f"TEST-SANDBOX-ORDER-{pid}",
                "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=TEST"}

    monkeypatch.setattr(paypal, "order", create)

    async def approved_order(order_id):
        # Direct capture must first verify buyer approval against the exact
        # locally registered Sandbox order. No provider network request.
        import app
        with app.db() as c:
            p=c.execute("SELECT * FROM payments WHERE order_id=?",(order_id,)).fetchone()
            assert p is not None
            return {
                "id":order_id,"intent":"CAPTURE","status":"APPROVED",
                "purchase_units":[{
                    "reference_id":f'{p["event_id"]}-{p["person_id"]}',
                    "custom_id":f'{p["event_id"]}:{p["person_id"]}',
                    "amount":{"currency_code":"USD","value":f'{p["amount_cents"]/100:.2f}'}
                }]
            }
    monkeypatch.setattr(paypal,"details",approved_order)


def prepare_orders(client, monkeypatch):
    event = first_event(client)
    mock_orders(monkeypatch)
    ids = [p["id"] for p in event["people"][:2]]
    for pid in ids:
        assert client.post(f"/api/events/{event['id']}/people/{pid}/approve").status_code == 200
        r = client.post(f"/api/paypal/orders/{event['id']}/{pid}")
        assert r.status_code == 200, r.text
    return event, ids


def matching_capture(amount, capture_id="CAPTURE-ONCE-777"):
    return {"purchase_units": [{"payments": {"captures": [{
        "id": capture_id, "status": "COMPLETED",
        "amount": {"currency_code": "USD", "value": f"{amount/100:.2f}"},
    }]}}]}


def test_capture_parser_rejects_ambiguous_and_malformed_data():
    valid = matching_capture(1100)
    assert paypal.completed_capture(valid, 1100)["id"] == "CAPTURE-ONCE-777"
    for bad in [
        None, [], {}, {"purchase_units": []},
        {"purchase_units": [valid["purchase_units"][0], valid["purchase_units"][0]]},
        {"purchase_units": [None]},
        {"purchase_units": [{"payments": None}]},
        {"purchase_units": [{"payments": {"captures": "not-a-list"}}]},
        {"purchase_units": [{"payments": {"captures": [None]}}]},
        {"purchase_units": [{"payments": {"captures": [
            valid["purchase_units"][0]["payments"]["captures"][0],
            valid["purchase_units"][0]["payments"]["captures"][0]
        ]}}]},
        {"purchase_units": [{"payments": {"captures": [{
            "id": "BAD ID", "status": "COMPLETED",
            "amount": {"currency_code": "USD", "value": "11.00"}
        }]}}]},
    ]:
        assert paypal.completed_capture(bad, 1100) is None
    assert paypal.completed_capture(valid, 1101) is None


def test_database_index_prevents_one_capture_id_on_two_payments(client):
    import app
    event = first_event(client)
    p1, p2 = event["people"][:2]
    with app.db() as conn:
        conn.execute(
            """INSERT INTO payments(event_id,person_id,order_id,amount_cents,
                request_id,capture_key,status,capture_id,created)
                VALUES(?,?,?,?,?,?,?,?,?)""",
            (event["id"], p1["id"], "INDEX-ORDER-1", 1100,
             "index-request-1", "index-cap-1", "completed",
             "CAPTURE-GLOBALLY-UNIQUE", app.now())
        )
    with pytest.raises(sqlite3.IntegrityError):
        with app.db() as conn:
            conn.execute(
                """INSERT INTO payments(event_id,person_id,order_id,amount_cents,
                    request_id,capture_key,status,capture_id,created)
                    VALUES(?,?,?,?,?,?,?,?,?)""",
                (event["id"], p2["id"], "INDEX-ORDER-2", 1100,
                 "index-request-2", "index-cap-2", "completed",
                 "CAPTURE-GLOBALLY-UNIQUE", app.now())
            )
    with app.db() as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM payments WHERE capture_id='CAPTURE-GLOBALLY-UNIQUE'"
        ).fetchone()[0] == 1


def test_direct_capture_reuse_keeps_second_payment_unverified(client, monkeypatch):
    event, people = prepare_orders(client, monkeypatch)
    amount = event["people"][0]["share_cents"]
    async def duplicate_capture(order_id, key):
        return matching_capture(amount)
    monkeypatch.setattr(paypal, "capture", duplicate_capture)
    r1 = client.post("/api/paypal/capture", json={"order_id":f"TEST-SANDBOX-ORDER-{people[0]}"})
    r2 = client.post("/api/paypal/capture", json={"order_id":f"TEST-SANDBOX-ORDER-{people[1]}"})
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 409, r2.text
    assert r2.json()["detail"] == "Sandbox capture is already assigned to another payment"
    fresh = first_event(client)
    assert fresh["sandbox_cents"] == amount
    assert fresh["people"][0]["status"] == "sandbox_paid"
    assert fresh["people"][1]["status"] == "unpaid"
    recovery = client.get("/api/paypal/recovery").json()
    assert recovery["summary"]["completed"] == 1
    assert recovery["summary"]["capturing"] == 1
    assert client.post("/api/paypal/capture",
        json={"order_id": f"TEST-SANDBOX-ORDER-{people[1]}"}).status_code == 409


def test_order_status_reuse_keeps_second_order_pending(client, monkeypatch):
    event, people = prepare_orders(client, monkeypatch)
    amount = event["people"][0]["share_cents"]
    async def details(order_id):
        pid = int(order_id.rsplit("-", 1)[-1])
        return {"id": order_id, "intent": "CAPTURE", "status": "COMPLETED",
                "purchase_units": [{
                    "custom_id": f"{event['id']}:{pid}",
                    "amount": {"currency_code": "USD", "value": f"{amount/100:.2f}"},
                    **matching_capture(amount)["purchase_units"][0],
                }]}
    monkeypatch.setattr(paypal, "details", details)
    good = client.post(f"/api/paypal/order-status/TEST-SANDBOX-ORDER-{people[0]}")
    reused = client.post(f"/api/paypal/order-status/TEST-SANDBOX-ORDER-{people[1]}")
    assert good.status_code == 200
    assert reused.status_code == 409
    assert first_event(client)["sandbox_cents"] == amount
    recovery = client.get("/api/paypal/recovery").json()
    assert recovery["summary"]["completed"] == 1
    assert recovery["summary"]["created"] == 1


def test_signed_webhook_reuse_does_not_double_count(client, monkeypatch):
    event, people = prepare_orders(client, monkeypatch)
    async def valid_signature(*args):
        return True
    monkeypatch.setattr(paypal, "verify_webhook", valid_signature)
    def event_payload(event_id, pid):
        return {"id": event_id, "event_type": "PAYMENT.CAPTURE.COMPLETED",
                "resource": {
                    "id": "CAPTURE-ONCE-777", "status": "COMPLETED",
                    "amount": {"currency_code": "USD", "value": "11.00"},
                    "supplementary_data": {"related_ids":
                        {"order_id": f"TEST-SANDBOX-ORDER-{pid}"}},
                }}
    first=event_payload("WEBHOOK-ONE", people[0])
    second=event_payload("WEBHOOK-TWO", people[1])
    assert client.post("/api/paypal/webhook", json=first).status_code == 200
    assert client.post("/api/paypal/webhook", json=first).json()["duplicate"] is True
    duplicate=client.post("/api/paypal/webhook", json=second)
    assert duplicate.status_code == 409
    assert first_event(client)["sandbox_cents"] == 1100
    recovery = client.get("/api/paypal/recovery").json()
    assert recovery["summary"]["completed"] == 1
    assert recovery["summary"]["created"] == 1
    import app
    with app.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM webhook_events").fetchone()[0] == 1


def test_ambiguous_multi_capture_response_never_unlocks_checkout(client, monkeypatch):
    event, people = prepare_orders(client, monkeypatch)
    amount = event["people"][0]["share_cents"]
    async def ambiguous_capture(order_id, key):
        item = matching_capture(amount)["purchase_units"][0]["payments"]["captures"][0]
        return {"purchase_units": [{"payments": {"captures": [item, dict(item, id="SECOND-CAPTURE")]}}]}
    monkeypatch.setattr(paypal, "capture", ambiguous_capture)
    result = client.post("/api/paypal/capture", json={"order_id": f"TEST-SANDBOX-ORDER-{people[0]}"})
    assert result.status_code == 409
    assert first_event(client)["sandbox_cents"] == 0
    recovery = client.get("/api/paypal/recovery").json()
    assert recovery["summary"]["capturing"] == 1
    assert client.post("/api/paypal/capture",
        json={"order_id": f"TEST-SANDBOX-ORDER-{people[0]}"}).status_code == 409
