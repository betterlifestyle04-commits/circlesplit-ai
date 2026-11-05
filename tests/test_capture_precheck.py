"""PayPal Sandbox capture preconditions and safe reconciliation.

Every provider response is mocked; no live PayPal calls or real money.
"""
import importlib
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
import paypal


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"capture-precheck.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def setup_order(client, monkeypatch):
    event=client.get("/api/state").json()["events"][0]
    person=event["people"][0]
    eid,pid,amount=event["id"],person["id"],person["share_cents"]
    monkeypatch.setattr(paypal,"configured",lambda:True)
    async def order(*args):
        return {"id":"TEST-CAPTURE-PRECHECK-ORDER",
                "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"}
    monkeypatch.setattr(paypal,"order",order)
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    created=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert created.status_code==200,created.text
    return eid,pid,amount,"TEST-CAPTURE-PRECHECK-ORDER"


def order_details(eid,pid,amount,order_id,status="APPROVED"):
    return {"id":order_id,"intent":"CAPTURE","status":status,
        "purchase_units":[{
            "custom_id":f"{eid}:{pid}","reference_id":f"{eid}-{pid}",
            "amount":{"currency_code":"USD","value":f"{amount/100:.2f}"}
        }]
    }


def local_state(client,order_id):
    import app
    with app.db() as c:
        return dict(c.execute("SELECT * FROM payments WHERE order_id=?",
                              (order_id,)).fetchone())


def no_capture(monkeypatch):
    calls=[]
    async def capture(*args):
        calls.append(args)
        raise AssertionError("Capture must not be sent")
    monkeypatch.setattr(paypal,"capture",capture)
    return calls


@pytest.mark.parametrize("provider_status",[
    "CREATED","PAYER_ACTION_REQUIRED","VOIDED","SAVED","UNKNOWN"
])
def test_nonapproved_provider_state_never_marks_capturing(
    client,monkeypatch,provider_status
):
    eid,pid,amount,oid=setup_order(client,monkeypatch)
    calls=no_capture(monkeypatch)
    async def get_details(*args):
        return order_details(eid,pid,amount,oid,provider_status)
    monkeypatch.setattr(paypal,"details",get_details)
    result=client.post("/api/paypal/capture",json={"order_id":oid})
    assert result.status_code==409,result.text
    assert "buyer approval" in result.json()["detail"]
    assert calls==[]
    assert local_state(client,oid)["status"]=="created"
    assert client.get("/api/paypal/recovery").json()["summary"]["created"]==1


@pytest.mark.parametrize("mutate",[
    lambda d: d.update(id="ANOTHER-ORDER"),
    lambda d: d.update(intent="AUTHORIZE"),
    lambda d: d["purchase_units"][0]["amount"].update(value="12.99"),
    lambda d: d["purchase_units"][0]["amount"].update(currency_code="EUR"),
    lambda d: d["purchase_units"][0].update(custom_id="999:999"),
    lambda d: d["purchase_units"][0].update(reference_id="999-999"),
    lambda d: d.update(purchase_units=[{},{}]),
    lambda d: d.update(purchase_units="invalid"),
])
def test_wrong_order_identity_amount_or_purpose_cannot_capture(
    client,monkeypatch,mutate
):
    eid,pid,amount,oid=setup_order(client,monkeypatch)
    calls=no_capture(monkeypatch)
    async def get_details(*args):
        detail=order_details(eid,pid,amount,oid)
        mutate(detail)
        return detail
    monkeypatch.setattr(paypal,"details",get_details)
    rejected=client.post("/api/paypal/capture",json={"order_id":oid})
    assert rejected.status_code==409,rejected.text
    assert calls==[]
    assert local_state(client,oid)["status"]=="created"


def test_provider_lookup_failure_does_not_lock_out_future_valid_capture(client,monkeypatch):
    eid,pid,amount,oid=setup_order(client,monkeypatch)
    calls=no_capture(monkeypatch)
    async def failed_details(*args):
        raise HTTPException(502,"PayPal Sandbox GET temporarily unavailable")
    monkeypatch.setattr(paypal,"details",failed_details)
    failed=client.post("/api/paypal/capture",json={"order_id":oid})
    assert failed.status_code==502
    assert local_state(client,oid)["status"]=="created"
    assert calls==[]
    # Later a valid, newly verified APPROVED order can be captured once.
    async def valid_details(*args):
        return order_details(eid,pid,amount,oid)
    monkeypatch.setattr(paypal,"details",valid_details)
    actual=[]
    async def capture(order_id,key):
        actual.append((order_id,key))
        return {"purchase_units":[{"payments":{"captures":[{
            "id":"CAPTURE-PRECHECK-VERIFIED","status":"COMPLETED",
            "amount":{"currency_code":"USD","value":f"{amount/100:.2f}"}
        }]}}]}
    monkeypatch.setattr(paypal,"capture",capture)
    good=client.post("/api/paypal/capture",json={"order_id":oid})
    assert good.status_code==200,good.text
    assert len(actual)==1
    assert local_state(client,oid)["status"]=="completed"
    assert client.post("/api/paypal/capture",json={"order_id":oid}).json()["already_recorded"] is True
    assert len(actual)==1


def test_already_completed_at_provider_reconciles_without_new_capture(client,monkeypatch):
    eid,pid,amount,oid=setup_order(client,monkeypatch)
    calls=no_capture(monkeypatch)
    async def completed_details(*args):
        d=order_details(eid,pid,amount,oid,"COMPLETED")
        d["purchase_units"][0]["payments"]={"captures":[{
            "id":"CAPTURE-EARLIER-777","status":"COMPLETED",
            "amount":{"currency_code":"USD","value":f"{amount/100:.2f}"}
        }]}
        return d
    monkeypatch.setattr(paypal,"details",completed_details)
    response=client.post("/api/paypal/capture",json={"order_id":oid})
    assert response.status_code==200,response.text
    assert response.json()["reconciled_only"] is True
    assert local_state(client,oid)["capture_id"]=="CAPTURE-EARLIER-777"
    assert local_state(client,oid)["status"]=="completed"
    assert calls==[]
    assert client.get("/api/state").json()["events"][0]["sandbox_cents"]==amount


def test_completed_without_single_matching_capture_stays_created(client,monkeypatch):
    eid,pid,amount,oid=setup_order(client,monkeypatch)
    calls=no_capture(monkeypatch)
    async def bad_details(*args):
        return order_details(eid,pid,amount,oid,"COMPLETED")
    monkeypatch.setattr(paypal,"details",bad_details)
    response=client.post("/api/paypal/capture",json={"order_id":oid})
    assert response.status_code==409
    assert local_state(client,oid)["status"]=="created"
    assert calls==[]


def test_second_local_settlement_during_provider_get_does_not_capture(client,monkeypatch):
    import app
    eid,pid,amount,oid=setup_order(client,monkeypatch)
    calls=no_capture(monkeypatch)
    async def provider_approved(*args):
        with app.db() as c:
            payment=c.execute("SELECT * FROM payments WHERE order_id=?",(oid,)).fetchone()
            app.settle_verified_sandbox_capture(c,payment,"CAPTURE-RACED-WEBHOOK")
        return order_details(eid,pid,amount,oid)
    monkeypatch.setattr(paypal,"details",provider_approved)
    response=client.post("/api/paypal/capture",json={"order_id":oid})
    assert response.status_code==200,response.text
    assert response.json()["already_recorded"] is True
    assert calls==[]
    assert local_state(client,oid)["capture_id"]=="CAPTURE-RACED-WEBHOOK"
