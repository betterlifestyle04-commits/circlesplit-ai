"""Guard late PayPal Sandbox GET / capture results against recreated SQLite.

Every provider call is mocked. No real money or provider API access.
"""
import importlib

import paypal
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path/"payment-epoch.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as t:
        yield t


def initial_order(client,monkeypatch):
    event=client.get("/api/state").json()["events"][0]
    eid=event["id"]
    p=event["people"][0]
    pid, amount=p["id"],p["share_cents"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    async def order(*args):
        return {
            "id":"TEST-RECON-EPOCH-ORDER-001",
            "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"
        }
    monkeypatch.setattr(paypal,"order",order)
    created=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert created.status_code==200,created.text
    import app
    with app.db() as c:
        row=dict(c.execute("SELECT * FROM payments WHERE order_id=?",
                          ("TEST-RECON-EPOCH-ORDER-001",)).fetchone())
    return row


def upstream(record,status):
    unit={
        "reference_id":f'{record["event_id"]}-{record["person_id"]}',
        "custom_id":f'{record["event_id"]}:{record["person_id"]}',
        "amount":{"currency_code":"USD","value":f'{record["amount_cents"]/100:.2f}'}
    }
    if status=="COMPLETED":
        unit["payments"]={"captures":[{
            "id":"TEST-RECON-EPOCH-CAPTURE-001",
            "status":"COMPLETED",
            "amount":{"currency_code":"USD",
                      "value":f'{record["amount_cents"]/100:.2f}'}
        }]}
    return {
        "id":record["order_id"],"intent":"CAPTURE",
        "status":status,"purchase_units":[unit]
    }


def reset_with_reused_payment_id(original, *, same_order=True, status="created"):
    """Emulate Render Free replacing SQLite while provider is responding."""
    import app
    app.DB.unlink()
    app.initialize()
    with app.db() as c:
        event=c.execute("SELECT id FROM events ORDER BY id LIMIT 1").fetchone()
        person=c.execute(
            "SELECT id FROM people WHERE event_id=? ORDER BY id LIMIT 1",
            (event["id"],)
        ).fetchone()
        c.execute(
            """INSERT INTO payments(event_id,person_id,amount_cents,
                request_id,capture_key,status,order_id,created)
               VALUES(?,?,?,?,?,?,?,?)""",
            (event["id"], person["id"], original["amount_cents"],
             "new-epoch-request-key", "new-epoch-capture-key",status,
             original["order_id"] if same_order else "NEW-RECON-ORDER",
             app.now())
        )
        row=dict(c.execute("SELECT * FROM payments ORDER BY id LIMIT 1").fetchone())
        assert row["id"]==original["id"],"The SQLite numeric payment ID was reused"
    return row


def local_payment():
    import app
    with app.db() as c:
        return dict(c.execute("SELECT * FROM payments ORDER BY id LIMIT 1").fetchone())


@pytest.mark.parametrize("status",["APPROVED","COMPLETED","CREATED"])
def test_status_get_cannot_reconcile_recreated_database(client,monkeypatch,status):
    original=initial_order(client,monkeypatch)
    async def details(order_id):
        assert order_id==original["order_id"]
        reset_with_reused_payment_id(original)
        return upstream(original,status)
    monkeypatch.setattr(paypal,"details",details)
    result=client.post("/api/paypal/order-status/"+original["order_id"])
    assert result.status_code==409,result.text
    assert "database changed" in result.json()["detail"]
    assert "do not retry" in result.json()["detail"]
    actual=local_payment()
    assert actual["status"]=="created"
    assert actual["capture_id"] is None
    assert actual["request_id"]=="new-epoch-request-key"


@pytest.mark.parametrize("status",["APPROVED","COMPLETED"])
def test_capture_get_cannot_trigger_new_charge_or_wrong_settlement_after_reset(
    client,monkeypatch,status
):
    original=initial_order(client,monkeypatch)
    calls=[]
    async def details(order_id):
        reset_with_reused_payment_id(original)
        return upstream(original,status)
    async def capture(*args):
        calls.append(args)
        raise AssertionError("No capture after a reset")
    monkeypatch.setattr(paypal,"details",details)
    monkeypatch.setattr(paypal,"capture",capture)
    result=client.post("/api/paypal/capture",json={"order_id":original["order_id"]})
    assert result.status_code==409,result.text
    assert "do not retry" in result.json()["detail"]
    assert calls==[]
    actual=local_payment()
    assert actual["status"]=="created"
    assert actual["capture_id"] is None


def test_capture_confirmation_cannot_settle_a_recreated_database(client,monkeypatch):
    original=initial_order(client,monkeypatch)
    async def details(order_id):
        return upstream(original,"APPROVED")
    calls=[]
    async def capture(order_id,key):
        calls.append((order_id,key))
        reset_with_reused_payment_id(original,same_order=True,status="capturing")
        return upstream(original,"COMPLETED")
    monkeypatch.setattr(paypal,"details",details)
    monkeypatch.setattr(paypal,"capture",capture)
    response=client.post("/api/paypal/capture",json={"order_id":original["order_id"]})
    assert response.status_code==409,response.text
    assert "database changed" in response.json()["detail"]
    assert len(calls)==1,"First and only Sandbox capture request was sent"
    current=local_payment()
    assert current["request_id"]=="new-epoch-request-key"
    assert current["status"]=="capturing"
    assert current["capture_id"] is None


@pytest.mark.parametrize("mode",["status","capture"])
def test_request_key_rewrite_blocks_late_provider_result(client,monkeypatch,mode):
    original=initial_order(client,monkeypatch)
    import app
    calls=[]
    async def details(order_id):
        with app.db() as c:
            c.execute("UPDATE payments SET request_id=? WHERE id=?",
                      ("other-request-key",original["id"]))
        return upstream(original,"COMPLETED" if mode=="status" else "APPROVED")
    async def capture(*args):
        calls.append(args)
        raise AssertionError("Must not capture after rewritten request")
    monkeypatch.setattr(paypal,"details",details)
    monkeypatch.setattr(paypal,"capture",capture)
    result=(client.post("/api/paypal/order-status/"+original["order_id"])
            if mode=="status"
            else client.post("/api/paypal/capture",json={
                "order_id":original["order_id"]
            }))
    assert result.status_code==409,result.text
    assert "record changed" in result.json()["detail"]
    assert calls==[]
    assert local_payment()["capture_id"] is None


def test_local_capture_response_cannot_attach_after_request_key_changed(client,monkeypatch):
    original=initial_order(client,monkeypatch)
    import app
    async def details(*args):
        return upstream(original,"APPROVED")
    async def capture(order_id,key):
        with app.db() as c:
            c.execute("UPDATE payments SET capture_key=? WHERE id=?",
                      ("other-capture-attempt",original["id"]))
        return upstream(original,"COMPLETED")
    monkeypatch.setattr(paypal,"details",details)
    monkeypatch.setattr(paypal,"capture",capture)
    result=client.post("/api/paypal/capture",json={
        "order_id":original["order_id"]
    })
    assert result.status_code==409,result.text
    assert "record changed" in result.json()["detail"]
    row=local_payment()
    assert row["status"]=="capturing"
    assert row["capture_id"] is None


def test_status_result_respects_new_local_capture_lock(client,monkeypatch):
    original=initial_order(client,monkeypatch)
    import app
    async def details(*args):
        with app.db() as c:
            c.execute("UPDATE payments SET status='capturing' WHERE id=?",
                      (original["id"],))
        return upstream(original,"APPROVED")
    monkeypatch.setattr(paypal,"details",details)
    response=client.post("/api/paypal/order-status/"+original["order_id"])
    assert response.status_code==200,response.text
    assert response.json()["action"]=="pending"
    assert response.json()["verified"] is False
    assert "already attempted" in response.json()["note"]
    assert local_payment()["status"]=="capturing"


def test_status_result_recognizes_already_verified_local_capture_after_get(
    client,monkeypatch
):
    original=initial_order(client,monkeypatch)
    import app
    async def details(*args):
        with app.db() as c:
            c.execute(
                "UPDATE payments SET status='completed',capture_id=? WHERE id=?",
                ("TEST-RECENT-VERIFIED-CAPTURE",original["id"])
            )
        return upstream(original,"APPROVED")
    monkeypatch.setattr(paypal,"details",details)
    result=client.post("/api/paypal/order-status/"+original["order_id"])
    assert result.status_code==200,result.text
    assert result.json()=={"status":"COMPLETED","action":"done","verified":True}


def test_status_get_rejects_mismatched_reference_id_and_malformed_upstream_data(
    client,monkeypatch
):
    original=initial_order(client,monkeypatch)
    invalid=[
        {"id":original["order_id"],"intent":"CAPTURE","status":"COMPLETED",
         "purchase_units":[None]},
        {"id":original["order_id"],"intent":"CAPTURE","status":"CREATED",
         "purchase_units":[{"amount":"11.00"}]},
        dict(upstream(original,"COMPLETED"),purchase_units=[
            dict(upstream(original,"COMPLETED")["purchase_units"][0],
                 reference_id="999-999")
        ]),
    ]
    for payload in invalid:
        async def details(*args):
            return payload
        monkeypatch.setattr(paypal,"details",details)
        res=client.post("/api/paypal/order-status/"+original["order_id"])
        assert res.status_code==409,res.text
        assert local_payment()["capture_id"] is None


def test_normal_status_verification_and_capture_remain_available(client,monkeypatch):
    original=initial_order(client,monkeypatch)
    async def details(*args):
        return upstream(original,"APPROVED")
    async def capture(*args):
        return upstream(original,"COMPLETED")
    monkeypatch.setattr(paypal,"details",details)
    monkeypatch.setattr(paypal,"capture",capture)
    check=client.post("/api/paypal/order-status/"+original["order_id"])
    assert check.status_code==200,check.text
    assert check.json()["action"]=="capture"
    settled=client.post("/api/paypal/capture",json={
        "order_id":original["order_id"]
    })
    assert settled.status_code==200,settled.text
    assert settled.json()["status"]=="completed"
    assert local_payment()["capture_id"]=="TEST-RECON-EPOCH-CAPTURE-001"
    check_again=client.post("/api/paypal/order-status/"+original["order_id"])
    assert check_again.status_code==200
    assert check_again.json()["verified"] is True
