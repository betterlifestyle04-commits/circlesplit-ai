"""Offline tests for complete, read-only PayPal Sandbox recovery pagination.

No real PayPal API calls, real money or current provider availability are tested.
"""
import importlib
import pytest
from fastapi.testclient import TestClient
import paypal


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"recovery.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def add_payment(conn, eid, pid, n, status, capture=None):
    import app
    conn.execute(
        """INSERT INTO payments(event_id,person_id,amount_cents,
                  request_id,capture_key,status,order_id,capture_id,created)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (eid,pid,1100,f"recover-request-{n}",f"recover-capture-key-{n}",
         status,f"RECOVER-SANDBOX-ORDER-{n}",capture,app.now())
    )


def test_full_ledger_counts_and_old_unresolved_order_first(client,monkeypatch):
    import app
    e=client.get("/api/state").json()["events"][0]
    eid=e["id"];pid=e["people"][0]["id"]
    with app.db() as c:
        add_payment(c,eid,pid,1,"creating")
        add_payment(c,eid,pid,2,"capturing")
        add_payment(c,eid,pid,3,"created")
        for n in range(4,235):
            add_payment(c,eid,pid,n,"completed",f"TEST-RECOVERY-CAPTURE-{n}")
    # Provider-backed methods must not be invoked by this read-only view.
    async def forbid_provider(*args,**kwargs):
        raise AssertionError("Recovery API must not contact PayPal")
    monkeypatch.setattr(paypal,"details",forbid_provider)
    monkeypatch.setattr(paypal,"capture",forbid_provider)
    page=client.get("/api/paypal/recovery?limit=10").json()
    assert page["total_records"]==234
    assert page["attention_count"]==3
    assert page["summary"]=={
        "creating":1,"created":1,"capturing":1,"completed":231,"other":0
    }
    assert page["returned"]==10 and page["limit"]==10 and page["offset"]==0
    assert page["next_offset"]==10 and page["is_truncated"] is True
    # Unresolved-first priority prevents the first/oldest payment being hidden.
    assert [x["status"] for x in page["items"][:3]]==[
        "created","capturing","creating"
    ]
    assert page["items"][2]["id"]==1
    assert page["items"][2]["order_id"] is None
    assert page["items"][1]["action"]=="check_existing_order"
    assert page["items"][1]["order_id"]=="RECOVER-SANDBOX-ORDER-2"
    assert page["items"][0]["order_id"]=="RECOVER-SANDBOX-ORDER-3"
    assert page["items"][3]["status"]=="completed"
    # Paginating does not change the full-ledger summary.
    later=client.get("/api/paypal/recovery?limit=10&offset=10").json()
    assert later["summary"]==page["summary"]
    assert later["attention_count"]==3
    assert later["items"][0]["id"]==227
    assert {x["id"] for x in later["items"]}.isdisjoint(
        {x["id"] for x in page["items"]}
    )
    assert client.get("/api/paypal/recovery?limit=10&offset=230").json()["next_offset"] is None
    assert client.get("/api/paypal/recovery?limit=10&offset=234").json()["items"]==[]


def test_corrupted_missing_capture_is_prioritized_and_counted(client):
    import app
    e=client.get("/api/state").json()["events"][0]
    eid=e["id"];pid=e["people"][0]["id"]
    with app.db() as c:
        add_payment(c,eid,pid,1,"completed",None)
        add_payment(c,eid,pid,2,"completed","RECOVER-CAPTURE-2")
        add_payment(c,eid,pid,3,"unknown-state")
    page=client.get("/api/paypal/recovery?limit=2").json()
    assert page["total_records"]==3
    assert page["attention_count"]==2
    assert page["summary"]["completed"]==2
    assert page["summary"]["other"]==1
    assert [x["id"] for x in page["items"]]==[3,1]
    assert all(x["action"]=="manual_review" for x in page["items"])
    assert all(x["order_id"] is None for x in page["items"])
    assert client.get("/api/paypal/recovery?limit=2&offset=2").json()["items"][0]["id"]==2


def test_orphan_payment_is_not_hidden_from_recovery_ledger(client):
    import app
    with app.db() as c:
        add_payment(c,99999,99999,1,"created")
    data=client.get("/api/paypal/recovery").json()
    assert data["total_records"]==1
    assert data["attention_count"]==1
    item=data["items"][0]
    assert item["action"]=="manual_review"
    assert item["event_name"]=="Missing local event"
    assert item["person_name"]=="Missing local participant"
    assert item["order_id"] is None
    assert "missing" in item["explanation"].lower()


@pytest.mark.parametrize("params",[
    "?limit=0","?limit=201","?limit=-1","?limit=no",
    "?offset=-1","?offset=too_big","?offset=1000001",
])
def test_recovery_rejects_unbounded_or_bad_pagination(client,params):
    response=client.get("/api/paypal/recovery"+params)
    assert response.status_code==422,response.text


def test_recovery_is_auth_protected_and_safe_with_pagination(client,monkeypatch):
    e=client.get("/api/state").json()["events"][0]
    pid=e["people"][0]["id"];eid=e["id"]
    link=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","private-demo-password-2026")
    route="/api/paypal/recovery?offset=0&limit=10"
    assert client.get(route).status_code==401
    assert client.get(route,headers={
        "Authorization":"Bearer "+link
    }).status_code==401
    authorized=client.get(route,auth=("judge","private-demo-password-2026"))
    assert authorized.status_code==200
    assert authorized.json()["total_records"]==0
    assert authorized.json()["offset"]==0
    assert authorized.json()["limit"]==10
    assert authorized.headers["Cache-Control"]=="no-store"
    assert client.get("/api/state",auth=("judge","private-demo-password-2026")).status_code==200
