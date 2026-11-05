"""Local-first PayPal Sandbox order creation must survive in-flight DB races.

All provider calls are mocked; no real money or PayPal API access.
"""
import importlib
import sqlite3

import paypal
import pytest
from fastapi.testclient import TestClient


CHECKOUT="https://www.sandbox.paypal.com/checkoutnow?token=TEST-SAFE"


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"orders.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def prepare(client, monkeypatch, idx=0):
    event=client.get("/api/state").json()["events"][0]
    eid=event["id"];pid=event["people"][idx]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    return eid,pid


def payment_rows():
    import app
    with app.db() as c:
        return [dict(row) for row in c.execute("SELECT * FROM payments ORDER BY id")]


def test_successful_provider_response_matches_original_persisted_request(client,monkeypatch):
    eid,pid=prepare(client,monkeypatch)
    async def remote_order(amount,event_id,person_id,url,key):
        assert event_id==eid and person_id==pid
        assert amount==1100
        assert url.endswith("/workspace?payment=return")
        with __import__("app").db() as c:
            payment=c.execute("SELECT * FROM payments WHERE person_id=?",(pid,)).fetchone()
            assert payment["status"]=="creating"
            assert payment["order_id"] is None
            assert payment["request_id"]==key
        return {"id":"SANDBOX-CAS-ORDER-001","approval_url":CHECKOUT}
    monkeypatch.setattr(paypal,"order",remote_order)
    response=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert response.status_code==200,response.text
    assert response.json()["order_id"]=="SANDBOX-CAS-ORDER-001"
    assert response.json()["mode"]=="PAYPAL_SANDBOX"
    row=payment_rows()[0]
    assert row["status"]=="created"
    assert row["order_id"]=="SANDBOX-CAS-ORDER-001"
    assert row["request_id"] and row["capture_key"]
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==409


@pytest.mark.parametrize("order_id",[
    None,12,"A","FOUR","/v2/checkout/orders","FAKE ORDER",
    "ÅBCDE-ORDER","X"*51,"\n1234567",
])
def test_untrusted_remote_order_id_cannot_be_recorded(client,monkeypatch,order_id):
    eid,pid=prepare(client,monkeypatch)
    async def invalid(*args):
        return {"id":order_id,"approval_url":CHECKOUT}
    monkeypatch.setattr(paypal,"order",invalid)
    result=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert result.status_code==502,result.text
    row=payment_rows()[0]
    assert row["status"]=="creating" and row["order_id"] is None
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==409


@pytest.mark.parametrize("url",[
    None,"https://example.com/checkout","http://www.sandbox.paypal.com/checkoutnow",
    "https://sandbox.paypal.com.evil.test/checkout",
    "https://sandbox.paypal.com@evil.test/checkout",
    "https://example.com@sandbox.paypal.com/checkout",
    "https://sandbox.paypal.com:444/checkoutnow",
    "https://sandbox.paypal.com:not-a-port/checkoutnow",
])
def test_untrusted_approval_link_cannot_be_returned(client,monkeypatch,url):
    eid,pid=prepare(client,monkeypatch)
    async def invalid(*args):
        return {"id":"VALID-SANDBOX-ORDER-001","approval_url":url}
    monkeypatch.setattr(paypal,"order",invalid)
    r=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert r.status_code==502,r.text
    assert payment_rows()[0]["status"]=="creating"
    assert payment_rows()[0]["order_id"] is None


def test_reset_while_paypal_request_in_flight_never_misattributed_to_reused_row(
    client,monkeypatch
):
    import app
    eid,pid=prepare(client,monkeypatch)
    before_epoch=client.get("/api/judge-readiness").json()["storage_epoch"]
    async def resets_database(*args):
        # Mimic Render Free losing the old database *after* order creation
        # was initiated and while PayPal returned a valid response.
        app.DB.unlink()
        app.initialize()
        new=client.get("/api/state").json()["events"][0]
        with app.db() as c:
            c.execute(
                """INSERT INTO payments(event_id,person_id,amount_cents,
                   request_id,capture_key,status,created)
                   VALUES(?,?,?,?,?,?,?)""",
                (new["id"],new["people"][0]["id"],1100,
                 "new-epoch-not-the-original-request","new-epoch-capture-key",
                 "creating",app.now())
            )
        return {"id":"OLD-EPOCH-REMOTE-ORDER","approval_url":CHECKOUT}
    monkeypatch.setattr(paypal,"order",resets_database)
    response=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert response.status_code==409,response.text
    assert "database changed" in response.json()["detail"]
    assert "do not retry" in response.json()["detail"]
    assert client.get("/api/judge-readiness").json()["storage_epoch"]!=before_epoch
    new_record=payment_rows()[0]
    assert new_record["id"]==1  # SQLite ID reused after recreated database.
    assert new_record["request_id"]=="new-epoch-not-the-original-request"
    assert new_record["order_id"] is None
    assert new_record["status"]=="creating"


def test_row_rewrite_while_provider_creates_order_is_rejected_without_attaching_id(
    client,monkeypatch
):
    import app
    eid,pid=prepare(client,monkeypatch)
    async def rewrites_request(*args):
        with app.db() as c:
            c.execute(
                "UPDATE payments SET request_id='different-creation-attempt' WHERE person_id=?",
                (pid,)
            )
        return {"id":"OLD-REQUEST-REMOTE-ORDER","approval_url":CHECKOUT}
    monkeypatch.setattr(paypal,"order",rewrites_request)
    result=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert result.status_code==409
    row=payment_rows()[0]
    assert row["request_id"]=="different-creation-attempt"
    assert row["status"]=="creating" and row["order_id"] is None


def test_two_payments_cannot_claim_same_paypal_order_id(client,monkeypatch):
    first_eid,first_pid=prepare(client,monkeypatch)
    async def duplicate(*args):
        return {"id":"IDENTICAL-SANDBOX-ORDER","approval_url":CHECKOUT}
    monkeypatch.setattr(paypal,"order",duplicate)
    assert client.post(f"/api/paypal/orders/{first_eid}/{first_pid}").status_code==200
    second_eid,second_pid=prepare(client,monkeypatch,1)
    conflict=client.post(f"/api/paypal/orders/{second_eid}/{second_pid}")
    assert conflict.status_code==409,conflict.text
    assert "conflicts" in conflict.json()["detail"]
    one,two=payment_rows()
    assert one["status"]=="created" and one["order_id"]=="IDENTICAL-SANDBOX-ORDER"
    assert two["status"]=="creating" and two["order_id"] is None


def test_validator_rejects_unicode_path_injection_and_long_ids():
    assert paypal.valid_sandbox_order_id("TEST-ORDER-001")
    assert not paypal.valid_sandbox_order_id("ÅBCDE123")
    assert not paypal.valid_sandbox_order_id("ABCDE/../../")
    assert not paypal.valid_sandbox_order_id("X"*51)
    assert not paypal.valid_sandbox_order_id("abcd")
    assert not paypal.valid_sandbox_order_id(None)
    assert paypal.trusted_sandbox_checkout_url(CHECKOUT)
    assert not paypal.trusted_sandbox_checkout_url(
        "https://sandbox.paypal.com:8443/checkoutnow")
    assert not paypal.trusted_sandbox_checkout_url(
        "https://name:pass@sandbox.paypal.com/checkoutnow")
    assert not paypal.trusted_sandbox_checkout_url(
        "https://sandbox.paypal.com:wrong/checkoutnow")


def test_check_order_endpoint_rejects_unicode_order_id_before_provider(client):
    result=client.post("/api/paypal/order-status/ÅBCDE")
    assert result.status_code==422
