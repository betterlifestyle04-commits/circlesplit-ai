"""Private sandbox reconciliation export: useful for manual review, never for restore.

No tests make real PayPal provider calls or transmit payment identifiers.
"""
import hashlib
import importlib
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
import paypal


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "sandbox-reconcile.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def seed_payment(c, eid, pid, n, status, *, capture=None, order=True):
    import app
    c.execute(
        """INSERT INTO payments(
              event_id,person_id,amount_cents,request_id,capture_key,
              order_id,capture_id,status,created)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (eid,pid,1100,"private-req-"+str(n),"private-cap-"+str(n),
         "ORDER-FOR-PRIVATE-EXPORT-"+str(n) if order else None,
         capture,status,app.now())
    )


def check_digest(manifest):
    serialized=json.dumps(manifest["records"], sort_keys=True,
                          separators=(",", ":"),ensure_ascii=False).encode("utf-8")
    assert hashlib.sha256(serialized).hexdigest()==manifest["records_sha256"]


def test_manifest_is_complete_private_and_self_describing(client,monkeypatch):
    import app
    event=client.get("/api/state").json()["events"][0]
    eid=event["id"];pid=event["people"][0]["id"]
    with app.db() as c:
        seed_payment(c,eid,pid,1,"creating",order=False)
        seed_payment(c,eid,pid,2,"created")
        seed_payment(c,eid,pid,3,"capturing")
        seed_payment(c,eid,pid,4,"completed",capture="CAPTURE-PRIVATE-SANDBOX-4")
    before=client.get("/api/state").json()
    history_before=client.get(f"/api/events/{eid}/history").json()
    async def no_paypal(*args,**kwargs):
        raise AssertionError("Export must not call PayPal")
    monkeypatch.setattr(paypal,"details",no_paypal)
    monkeypatch.setattr(paypal,"capture",no_paypal)
    response=client.get("/api/paypal/reconciliation-export")
    assert response.status_code==200,response.text
    assert "private" in response.headers["Cache-Control"]
    assert "no-store" in response.headers["Cache-Control"]
    assert response.headers["X-Content-Type-Options"]=="nosniff"
    assert response.headers["Referrer-Policy"]=="no-referrer"
    assert response.headers["Content-Disposition"].startswith("attachment;")
    manifest=response.json()
    assert manifest["kind"]=="paypal-sandbox-reconciliation-manifest"
    assert manifest["schema_version"]==1
    assert manifest["app"]=="CircleSplit AI"
    assert manifest["mode"]=="PAYPAL_SANDBOX"
    assert manifest["currency"]=="USD"
    assert manifest["record_count"]==4
    assert manifest["importable"] is False
    assert len(manifest["records"])==4
    assert [r["status"] for r in manifest["records"]]==[
        "creating","created","capturing","completed"
    ]
    assert manifest["records"][0]["paypal_order_id"] is None
    assert manifest["records"][3]["paypal_capture_id"]=="CAPTURE-PRIVATE-SANDBOX-4"
    assert manifest["records"][3]["amount_cents"]==1100
    assert manifest["records"][3]["participant_name"]=="Alex"
    assert manifest["records"][3]["event_name"]=="Friday Community Volleyball"
    assert len(manifest["storage_epoch"])==36
    datetime.fromisoformat(manifest["generated_at"])
    assert "not a paypal receipt" in manifest["limitations"].lower()
    check_digest(manifest)
    assert client.get("/api/state").json()==before
    assert client.get(f"/api/events/{eid}/history").json()==history_before
    dumped=response.text.lower()
    for forbidden in ("private-req-1","private-cap-1",
                      "paypal_client_secret","gemini_api_key",
                      "token_hash","webhook_events","approval_withdrawn_at"):
        assert forbidden not in dumped
    # This financial snapshot must not be accepted by planning-only restore.
    attempted=client.post("/api/planning-backup/restore",json=manifest)
    assert attempted.status_code==422
    assert client.get("/api/state").json()==before


def test_manifest_includes_all_records_beyond_recovery_page(client):
    import app
    event=client.get("/api/state").json()["events"][0]
    eid=event["id"];pid=event["people"][0]["id"]
    with app.db() as c:
        for n in range(1,266):
            seed_payment(c,eid,pid,n,"created" if n==1 else "completed",
                         capture=None if n==1 else f"CAPTURE-EXPORT-{n}")
    payload=client.get("/api/paypal/reconciliation-export").json()
    assert payload["record_count"]==265
    assert payload["records"][0]["payment_id"]==1
    assert payload["records"][-1]["payment_id"]==265
    assert sum(x["status"]=="created" for x in payload["records"])==1
    check_digest(payload)
    page=client.get("/api/paypal/recovery").json()
    assert page["returned"]==50
    assert page["total_records"]==payload["record_count"]


def test_export_does_not_omit_orphaned_records(client):
    import app
    with app.db() as c:
        seed_payment(c,999999,999999,1,"capturing")
    manifest=client.get("/api/paypal/reconciliation-export").json()
    assert manifest["record_count"]==1
    row=manifest["records"][0]
    assert row["event_name"] is None
    assert row["participant_name"] is None
    assert row["paypal_order_id"]=="ORDER-FOR-PRIVATE-EXPORT-1"
    check_digest(manifest)


def test_export_respects_hosted_auth_and_blocks_invitation_bearer(client,monkeypatch):
    event=client.get("/api/state").json()["events"][0]
    eid=event["id"];pid=event["people"][0]["id"]
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","very-long-fake-judge-secret")
    path="/api/paypal/reconciliation-export"
    assert client.get(path).status_code==401
    assert client.get(path,headers={"Authorization":"Bearer "+token}).status_code==401
    authorized=client.get(path,auth=("judge","very-long-fake-judge-secret"))
    assert authorized.status_code==200
    assert authorized.json()["record_count"]==0
    assert authorized.json()["storage_epoch"]
    assert "no-store" in authorized.headers["Cache-Control"]
    assert client.get("/health").json().get("storage_epoch") is None


def test_export_rejects_oversized_ledger_without_partial_file(client):
    import app
    e=client.get("/api/state").json()["events"][0]
    eid=e["id"];pid=e["people"][0]["id"]
    with app.db() as c:
        entries=[
            (eid,pid,1100,f"export-oversize-req-{n}",f"export-oversize-cap-{n}",
             "completed",f"CAPTURE-OVERSIZE-{n}",app.now())
            for n in range(10001)
        ]
        c.executemany(
            """INSERT INTO payments(event_id,person_id,amount_cents,
                      request_id,capture_key,status,capture_id,created)
               VALUES(?,?,?,?,?,?,?,?)""",entries
        )
    response=client.get("/api/paypal/reconciliation-export")
    assert response.status_code==413
    assert "Too many local sandbox payment records" in response.json()["detail"]
    assert client.get("/api/paypal/recovery?limit=1").json()["total_records"]==10001
