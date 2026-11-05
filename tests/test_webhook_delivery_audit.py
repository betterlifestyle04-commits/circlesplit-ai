"""Signed PayPal Sandbox webhook delivery triage, with mocked verification.

Tests exercise malformed upstream payloads, unknown orders, exact-cent
settlement, replay safety and read-only operator views. No live API calls.
"""
import importlib
import json
import sqlite3
from datetime import datetime, timedelta, timezone

import paypal
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"signed-webhooks.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED",raising=False)
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as test:
        yield test


def hooks():
    import app
    with app.db() as c:
        return [dict(x) for x in c.execute(
            "SELECT id,created,outcome FROM webhook_events ORDER BY id"
        )]


def first_payment(client,monkeypatch):
    e=client.get("/api/state").json()["events"][0]
    pid=e["people"][0]["id"]
    assert client.post(f"/api/events/{e['id']}/people/{pid}/approve").status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    async def order(*args):
        return {"id":"WEBHOOK-TRIAGE-ORDER-001",
                "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"}
    monkeypatch.setattr(paypal,"order",order)
    r=client.post(f"/api/paypal/orders/{e['id']}/{pid}")
    assert r.status_code==200,r.text
    return e["id"],pid,e["people"][0]["share_cents"]


def capture_event(event_id,order_id="WEBHOOK-TRIAGE-ORDER-001",
                  value="11.00",currency="USD"):
    return {"id":event_id,"event_type":"PAYMENT.CAPTURE.COMPLETED",
            "resource":{
                "id":"CAPTURE-TRIAGE-01","status":"COMPLETED",
                "amount":{"currency_code":currency,"value":value},
                "supplementary_data":{"related_ids":{"order_id":order_id}},
            }}


def mock_verified(monkeypatch):
    calls=[]
    async def verifier(headers,ev):
        calls.append(ev)
        return True
    monkeypatch.setattr(paypal,"verify_webhook",verifier)
    return calls


def audit(client):
    r=client.get("/api/paypal/webhook-audit")
    assert r.status_code==200,r.text
    return r.json()


def test_signed_unknown_capture_is_visible_and_never_considered_settled(client,monkeypatch):
    calls=mock_verified(monkeypatch)
    e=capture_event("WH-UNMATCHED-001","UNKNOWN-SBX-ORDER-009")
    r=client.post("/api/paypal/webhook",json=e)
    assert r.status_code==200,r.text
    assert r.json()=={"ok":True,"needs_manual_review":True}
    assert len(calls)==1
    summary=audit(client)
    assert summary["mode"]=="PAYPAL_SANDBOX"
    assert summary["source"]=="current_local_sqlite_signed_events_only"
    assert summary["total_events"]==1
    assert summary["manual_review_events"]==1
    assert summary["outcomes"]["unmatched_order"]==1
    assert "UNKNOWN-SBX" not in str(summary)
    assert "CAPTURE-TRIAGE-01" not in str(summary)
    assert "WH-UNMATCHED-001" not in str(summary)
    assert len(hooks())==1
    replay=client.post("/api/paypal/webhook",json=e)
    assert replay.status_code==200
    assert replay.json()=={"ok":True,"duplicate":True}
    assert len(hooks())==1
    assert audit(client)==summary


@pytest.mark.parametrize("resource,expected",[
    (None,"missing_order_reference"),
    ([],"missing_order_reference"),
    ({"supplementary_data":None},"missing_order_reference"),
    ({"supplementary_data":{"related_ids":None}},"missing_order_reference"),
    ({"supplementary_data":{"related_ids":{"order_id":[]} }},"missing_order_reference"),
    ({"supplementary_data":{"related_ids":{"order_id":"SHORT"}}},"unmatched_order"),
])
def test_unexpected_signed_resource_shapes_never_raise_500(
    client,monkeypatch,resource,expected
):
    mock_verified(monkeypatch)
    e={"id":"WH-MALFORMED-100","event_type":"PAYMENT.CAPTURE.COMPLETED",
       "resource":resource}
    r=client.post("/api/paypal/webhook",json=e)
    assert r.status_code==200,r.text
    assert r.json()["needs_manual_review"] is True
    assert audit(client)["outcomes"][expected]==1


@pytest.mark.parametrize("modify,outcome",[
    (lambda x:x["resource"].update(status="PENDING"),"invalid_capture_payload"),
    (lambda x:x["resource"].update(id=None),"invalid_capture_payload"),
    (lambda x:x["resource"].update(id="BAD CAPTURE ID"),"invalid_capture_payload"),
    (lambda x:x["resource"].update(amount=[]),"invalid_capture_payload"),
    (lambda x:x["resource"].update(amount={}),"amount_or_currency_mismatch"),
    (lambda x:x["resource"]["amount"].update(value="11.01"),"amount_or_currency_mismatch"),
    (lambda x:x["resource"]["amount"].update(currency_code="EUR"),"amount_or_currency_mismatch"),
])
def test_signed_wrong_capture_data_is_audited_without_settlement(
    client,monkeypatch,modify,outcome
):
    first_payment(client,monkeypatch)
    mock_verified(monkeypatch)
    e=capture_event("WH-INVALID-001")
    modify(e)
    r=client.post("/api/paypal/webhook",json=e)
    assert r.status_code==200,r.text
    assert r.json()["needs_manual_review"] is True
    result=audit(client)
    assert result["manual_review_events"]==1
    assert result["outcomes"][outcome]==1
    assert client.get("/api/state").json()["events"][0]["sandbox_cents"]==0


def test_signed_valid_capture_settles_once_and_classifies_replay(client,monkeypatch):
    first_payment(client,monkeypatch)
    mock_verified(monkeypatch)
    event=capture_event("WH-SETTLED-001")
    posted=client.post("/api/paypal/webhook",json=event)
    assert posted.status_code==200,posted.text
    assert posted.json()["needs_manual_review"] is False
    assert client.get("/api/state").json()["events"][0]["sandbox_cents"]==1100
    assert audit(client)["outcomes"]["capture_recorded"]==1
    assert client.post("/api/paypal/webhook",json=event).json()["duplicate"] is True
    next_event=capture_event("WH-SETTLED-REPEAT-002")
    assert client.post("/api/paypal/webhook",json=next_event).status_code==200
    assert audit(client)["outcomes"]["capture_already_recorded"]==1
    assert audit(client)["total_events"]==2
    assert client.get("/api/state").json()["events"][0]["sandbox_cents"]==1100


def test_unrelated_valid_signed_event_is_classified_without_attempting_payment(
    client,monkeypatch
):
    calls=mock_verified(monkeypatch)
    response=client.post("/api/paypal/webhook",json={
        "id":"WH-OTHER-001","event_type":"CHECKOUT.ORDER.APPROVED",
        "resource":None
    })
    assert response.status_code==200
    assert response.json()["needs_manual_review"] is False
    assert audit(client)["outcomes"]["ignored_event_type"]==1
    assert audit(client)["manual_review_events"]==0
    assert len(calls)==1


@pytest.mark.parametrize("payload",[
    [],[1],None,"PAYPAL EVENT",123,
    {"id":None,"event_type":"PAYMENT.CAPTURE.COMPLETED"},
    {"id":"A"*129,"event_type":"PAYMENT.CAPTURE.COMPLETED"},
    {"id":"WH BAD SPACE","event_type":"PAYMENT.CAPTURE.COMPLETED"},
    {"id":"WH-\u2603","event_type":"PAYMENT.CAPTURE.COMPLETED"},
])
def test_bad_event_envelope_or_id_rejected_before_remote_verification(
    client,monkeypatch,payload
):
    calls=mock_verified(monkeypatch)
    response=client.post("/api/paypal/webhook",json=payload)
    assert response.status_code==400,response.text
    assert calls==[] and hooks()==[]


def test_bad_signature_never_records_or_settles_even_with_provider_order(
    client,monkeypatch
):
    first_payment(client,monkeypatch)
    async def bad_signature(*args):
        raise HTTPException(401,"Invalid webhook signature")
    monkeypatch.setattr(paypal,"verify_webhook",bad_signature)
    r=client.post("/api/paypal/webhook",
                  json=capture_event("WH-INVALID-SIGNATURE"))
    assert r.status_code==401
    assert audit(client)["total_events"]==0
    assert client.get("/api/state").json()["events"][0]["sandbox_cents"]==0


def test_legacy_signed_webhooks_are_not_falsely_classified_as_captures(
    client,monkeypatch
):
    import app
    with app.db() as c:
        c.execute("DROP TABLE webhook_events")
        c.execute("""CREATE TABLE webhook_events (
                     id TEXT PRIMARY KEY, created TEXT NOT NULL)""")
        c.execute("INSERT INTO webhook_events(id,created) VALUES (?,?)",
                  ("WH-LEGACY-001",app.now()))
    app.initialize()
    current=hooks()
    assert current[0]["outcome"]=="legacy_unclassified"
    summary=audit(client)
    assert summary["total_events"]==1
    assert summary["manual_review_events"]==1
    assert summary["outcomes"]["legacy_unclassified"]==1
    # Startup migration is idempotent and preserves the existing event ID.
    app.initialize()
    assert hooks()==current


def test_webhook_audit_is_private_read_only_and_never_calls_paypal(
    client,monkeypatch
):
    mock_verified(monkeypatch)
    client.post("/api/paypal/webhook",json=capture_event("WH-AUDIT-001"))
    before=hooks()
    async def forbid(*args):
        raise AssertionError("Read-only audit must not contact provider")
    monkeypatch.setattr(paypal,"details",forbid)
    monkeypatch.setattr(paypal,"capture",forbid)
    monkeypatch.setattr(paypal,"verify_webhook",forbid)
    for _ in range(3):
        r=client.get("/api/paypal/webhook-audit")
        assert r.status_code==200
        assert "no-store" in r.headers["Cache-Control"]
    assert hooks()==before
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_USERNAME","owner")
    monkeypatch.setenv("DEMO_PASSWORD","private-local-owner-password")
    assert client.get("/api/paypal/webhook-audit").status_code==401
    authorized=client.get("/api/paypal/webhook-audit",
                          auth=("owner","private-local-owner-password"))
    assert authorized.status_code==200
    assert authorized.json()["total_events"]==1


def test_capture_reuse_conflict_remains_fail_closed_and_unacknowledged(
    client,monkeypatch
):
    # Distinct PayPal orders may never reuse the same provider capture ID.
    first_payment(client,monkeypatch)
    mock_verified(monkeypatch)
    first=client.post("/api/paypal/webhook",
        json=capture_event("WH-FIRST-001"))
    assert first.status_code==200
    import app
    eid=client.get("/api/state").json()["events"][0]["id"]
    pid=client.get("/api/state").json()["events"][0]["people"][1]["id"]
    with app.db() as c:
        c.execute(
            """INSERT INTO payments(event_id,person_id,amount_cents,
                request_id,capture_key,status,order_id,created)
               VALUES(?,?,?,?,?,?,?,?)""",
            (eid,pid,1100,"second-request-key","second-capture-key",
             "created","SECOND-WEBHOOK-ORDER-100",app.now())
        )
    dup=capture_event("WH-DUPLICATE-CAPTURE-002",
                      order_id="SECOND-WEBHOOK-ORDER-100")
    blocked=client.post("/api/paypal/webhook",json=dup)
    assert blocked.status_code==409
    assert "already assigned" in blocked.json()["detail"]
    # The second event cannot be acknowledged as successfully processed.
    assert audit(client)["total_events"]==1
    with app.db() as c:
        second=c.execute("SELECT status,capture_id FROM payments WHERE order_id=?",
                         ("SECOND-WEBHOOK-ORDER-100",)).fetchone()
        assert second["status"]=="created" and second["capture_id"] is None
