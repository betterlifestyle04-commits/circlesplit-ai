"""Hosted judge credential separation for PayPal Sandbox provider actions.

All provider calls are mocked and no real money is processed.
"""
from datetime import datetime, timedelta, timezone
import importlib

import paypal
import pytest
from fastapi.testclient import TestClient
from security import owner_only_sandbox_action


OWNER=("owner-demo","owner-demo-secret-absolutely-private")
JUDGE=("judge-demo","judge-demo-secret-absolutely-private")


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"judge-payments.sqlite3"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("PUBLIC_BASE_URL","https://circlesplit-ai-demo.onrender.com")
    monkeypatch.setenv("DEMO_USERNAME",OWNER[0])
    monkeypatch.setenv("DEMO_PASSWORD",OWNER[1])
    monkeypatch.setenv("JUDGE_ACCESS_ENABLED","1")
    monkeypatch.setenv("JUDGE_USERNAME",JUDGE[0])
    monkeypatch.setenv("JUDGE_PASSWORD",JUDGE[1])
    monkeypatch.setenv("JUDGE_ACCESS_EXPIRES_AT",
        (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat())
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def pick(client):
    e=client.get("/api/state",auth=OWNER).json()["events"][0]
    return e["id"],e["people"][0]["id"]


def audit_rows():
    import app
    with app.db() as c:
        return [dict(x) for x in c.execute("SELECT * FROM payments ORDER BY id")]


def test_helper_covers_future_post_routes_without_blocking_signed_webhooks():
    assert owner_only_sandbox_action("POST","/api/paypal/capture")
    assert owner_only_sandbox_action("POST","/api/paypal/order-status/TEST-ORDER")
    assert owner_only_sandbox_action("POST","/api/paypal/orders/1/1")
    assert owner_only_sandbox_action("POST","/api/paypal/future-financial-action")
    assert not owner_only_sandbox_action("POST","/api/paypal/webhook")
    assert not owner_only_sandbox_action("GET","/api/paypal/recovery")
    assert not owner_only_sandbox_action("POST","/api/participant/approve")
    assert not owner_only_sandbox_action("POST","/api/paypal/webhook/extra")


def test_judge_can_inspect_and_simulate_but_cannot_start_sandbox_order(
    client,monkeypatch
):
    eid,pid=pick(client)
    assert client.post(f"/api/events/{eid}/people/{pid}/approve",
                       auth=OWNER).status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    calls=[]
    async def forbid_order(*args):
        calls.append(args)
        raise AssertionError("Judge must not reach PayPal")
    monkeypatch.setattr(paypal,"order",forbid_order)
    owner_state=client.get("/api/state",auth=OWNER)
    judge_state=client.get("/api/state",auth=JUDGE)
    assert owner_state.status_code==judge_state.status_code==200
    assert owner_state.json()["viewer_role"]=="owner"
    assert owner_state.json()["sandbox_order_actions_allowed"] is True
    assert judge_state.json()["viewer_role"]=="judge"
    assert judge_state.json()["sandbox_order_actions_allowed"] is False
    pre=client.get(f"/api/paypal/checkout-readiness/{eid}/{pid}",auth=JUDGE)
    assert pre.status_code==200
    assert not pre.json()["can_create_order"]
    assert "organizer_credentials_required" in [p["code"] for p in pre.json()["blockers"]]
    assert "no-store" in pre.headers["Cache-Control"]
    assert client.get(f"/api/paypal/checkout-readiness/{eid}/{pid}",
                      auth=OWNER).json()["can_create_order"] is True
    r=client.post(f"/api/paypal/orders/{eid}/{pid}",auth=JUDGE)
    assert r.status_code==403
    assert "Organizer credentials" in r.json()["detail"]
    assert "no-store" in r.headers["Cache-Control"]
    assert not calls
    assert audit_rows()==[]
    # Judge still has access to the fictional, in-process exercise mode.
    demo=client.post(f"/api/events/{eid}/people/{pid}/simulate",auth=JUDGE)
    assert demo.status_code==200
    assert demo.json()["mode"]=="SIMULATED - NOT PAYPAL"
    assert audit_rows()==[]


def test_judge_cannot_reconcile_or_capture_even_with_known_order(client,monkeypatch):
    eid,pid=pick(client)
    assert client.post(f"/api/events/{eid}/people/{pid}/approve",
                       auth=OWNER).status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    async def create_order(*args):
        return {"id":"OWNER-SANDBOX-ORDER-1001",
                "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"}
    monkeypatch.setattr(paypal,"order",create_order)
    r=client.post(f"/api/paypal/orders/{eid}/{pid}",auth=OWNER)
    assert r.status_code==200,r.text
    before=audit_rows()
    assert len(before)==1 and before[0]["status"]=="created"
    calls=[]
    async def forbid(*args):
        calls.append(args)
        raise AssertionError("Judge must not make a provider call")
    monkeypatch.setattr(paypal,"details",forbid)
    monkeypatch.setattr(paypal,"capture",forbid)
    oid=r.json()["order_id"]
    for path,payload in [
        ("/api/paypal/order-status/"+oid,None),
        ("/api/paypal/capture",{"order_id":oid}),
        (f"/api/paypal/orders/{eid}/{pid}",None),
        ("/api/paypal/future-financial-action",None),
    ]:
        denied=client.post(path,auth=JUDGE,json=payload)
        assert denied.status_code==403,(path,denied.text)
        assert "Organizer credentials" in denied.json()["detail"]
    assert calls==[]
    assert audit_rows()==before
    assert client.get("/api/paypal/recovery",auth=JUDGE).status_code==200
    assert client.get("/api/paypal/ledger-audit",auth=JUDGE).status_code==200
    assert client.get("/api/paypal/reconciliation-export",auth=JUDGE).status_code==403
    # Owner-initiated GET order verification is still available.
    async def provider_details(order_id):
        return {"id":order_id,"intent":"CAPTURE","status":"APPROVED",
                "purchase_units":[{"custom_id":f"{eid}:{pid}",
                                   "reference_id":f"{eid}-{pid}",
                                   "amount":{"currency_code":"USD","value":"11.00"}}]}
    monkeypatch.setattr(paypal,"details",provider_details)
    owner=client.post("/api/paypal/order-status/"+oid,auth=OWNER)
    assert owner.status_code==200,owner.text
    assert owner.json()["action"]=="capture"


def test_expired_or_disabled_judge_password_cannot_access_workspace(
    client,monkeypatch
):
    assert client.get("/workspace",auth=JUDGE).status_code==200
    monkeypatch.setenv("JUDGE_ACCESS_EXPIRES_AT",
                      (datetime.now(timezone.utc)-timedelta(seconds=30)).isoformat())
    assert client.get("/workspace",auth=JUDGE).status_code==401
    assert client.get("/api/state",auth=JUDGE).status_code==401
    assert client.get("/api/state",auth=OWNER).status_code==200
    monkeypatch.setenv("JUDGE_ACCESS_EXPIRES_AT",
                      (datetime.now(timezone.utc)+timedelta(hours=2)).isoformat())
    monkeypatch.setenv("JUDGE_ACCESS_ENABLED","0")
    assert client.get("/workspace",auth=JUDGE).status_code==401


def test_signed_webhook_is_not_blocked_by_judge_owner_role_boundary(client):
    # Webhooks must reach signature verification even without Basic creds.
    response=client.post("/api/paypal/webhook",json={"id":"SANDBOX-WEBHOOK-1"})
    assert response.status_code==503,response.text
    assert "Organizer credentials" not in response.text


def test_unauthenticated_and_bearer_client_cannot_impersonate_owner(client):
    eid,pid=pick(client)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==401
    response=client.post(f"/api/paypal/orders/{eid}/{pid}",headers={
        "Authorization":"Bearer arbitrary-jwt-test"
    })
    assert response.status_code==401
    assert client.get("/api/state").status_code==401
