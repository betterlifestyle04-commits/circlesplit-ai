"""Full local PayPal Sandbox consistency audit. All provider calls are mocked."""
import importlib
from fastapi.testclient import TestClient
import pytest
import paypal


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"audit.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as c:
        yield c


def context(client):
    e=client.get("/api/state").json()["events"][0]
    return e["id"],e["people"][0]["id"],e["people"][0]["share_cents"]


def payment(c,eid,pid,n,status="created",amount=1100,order=True,capture=None):
    import app
    c.execute(
        """INSERT INTO payments(event_id,person_id,amount_cents,request_id,capture_key,
               order_id,capture_id,status,created) VALUES(?,?,?,?,?,?,?,?,?)""",
        (eid,pid,amount,f"audit-request-{n}",f"audit-key-{n}",
         f"AUDIT-ORDER-{n}" if order else None,capture,status,app.now())
    )


def test_empty_local_audit_is_consistent_without_provider_calls(client,monkeypatch):
    async def no_external(*args,**kwargs):
        raise AssertionError("Audit must never contact PayPal")
    monkeypatch.setattr(paypal,"details",no_external)
    monkeypatch.setattr(paypal,"capture",no_external)
    before=client.get("/api/state").json()
    result=client.get("/api/paypal/ledger-audit")
    assert result.status_code==200,result.text
    report=result.json()
    assert report["status"]=="locally_consistent"
    assert report["payment_records_checked"]==0
    assert report["issue_count"]==0
    assert report["unresolved_orders"]==0
    assert report["findings"]==[]
    assert "no-store" in result.headers["Cache-Control"]
    assert client.get("/api/state").json()==before


def test_valid_pending_and_completed_capture_are_not_false_alarms(client):
    import app
    eid,pid,amount=context(client)
    with app.db() as c:
        payment(c,eid,pid,1,"created",amount)
    pending=client.get("/api/paypal/ledger-audit").json()
    assert pending["unresolved_orders"]==1
    assert pending["status"]=="locally_consistent"
    assert pending["issue_count"]==0
    with app.db() as c:
        c.execute("UPDATE payments SET status='completed',capture_id=? WHERE person_id=?",
                  ("AUDIT-CAPTURE-1",pid))
        c.execute("UPDATE people SET status='sandbox_paid' WHERE id=?",(pid,))
    completed=client.get("/api/paypal/ledger-audit").json()
    assert completed["status"]=="locally_consistent"
    assert completed["unresolved_orders"]==0
    assert completed["issue_count"]==0


def test_corrupt_ledger_discloses_specific_anomaly_categories(client):
    import app
    eid,pid,amount=context(client)
    second=client.get("/api/state").json()["events"][0]["people"][1]["id"]
    with app.db() as c:
        payment(c,eid,pid,1,"completed",amount,order=False,capture=None)
        payment(c,eid,pid,2,"capturing",amount+2,capture="CAPTURE-UNCONFIRMED")
        payment(c,eid,999999,3,"created",amount)
        payment(c,999999,second,4,"created",amount)
        payment(c,eid,second,5,"unrecognized",amount)
        c.execute("UPDATE people SET status='sandbox_paid' WHERE id=?",(second,))
    snapshot=client.get("/api/paypal/reconciliation-export").json()
    result=client.get("/api/paypal/ledger-audit").json()
    counts=result["issue_counts"]
    for key in [
        "completed_without_capture",
        "completed_person_not_paid",
        "missing_paypal_order_id",
        "payment_amount_mismatch",
        "capture_on_incomplete_payment",
        "missing_participant",
        "missing_event",
        "payment_event_mismatch",
        "invalid_payment_status",
        "multiple_paypal_orders_for_person",
        "paid_person_without_capture",
    ]:
        assert counts.get(key,0)>0,key
    assert result["status"]=="needs_review"
    assert result["payment_records_checked"]==5
    assert result["unresolved_orders"]==4
    assert result["issue_count"]==sum(counts.values())
    assert result["findings_truncated"] is False
    # Audit cannot modify the existing reconciliation manifest or payment rows.
    after=client.get("/api/paypal/reconciliation-export").json()
    assert snapshot["records"]==after["records"]
    assert snapshot["records_sha256"]==after["records_sha256"]
    assert "paypal_order_id" not in str(result)
    assert "participant_name" not in str(result)


def test_demo_paid_participant_with_paypal_order_is_flagged(client):
    import app
    eid,pid,amount=context(client)
    with app.db() as c:
        payment(c,eid,pid,1,"created",amount)
        c.execute("UPDATE people SET status='demo_paid' WHERE id=?",(pid,))
    report=client.get("/api/paypal/ledger-audit").json()
    assert report["issue_counts"]["simulated_person_has_paypal_order"]==1


def test_findings_cap_does_not_truncate_global_counts(client):
    import app
    eid,pid,amount=context(client)
    with app.db() as c:
        for n in range(1,131):
            payment(c,eid,pid,n,"unexpected",amount)
    report=client.get("/api/paypal/ledger-audit").json()
    assert report["payment_records_checked"]==130
    assert report["unresolved_orders"]==130
    assert report["issue_counts"]["invalid_payment_status"]==130
    assert report["issue_counts"]["multiple_paypal_orders_for_person"]==1
    assert report["issue_count"]==131
    assert len(report["findings"])==100
    assert report["findings_truncated"] is True


def test_global_audit_is_organizer_authenticated_and_not_visible_via_invitation(client,monkeypatch):
    eid,pid,amount=context(client)
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","unique-long-audit-judge-secret")
    route="/api/paypal/ledger-audit"
    assert client.get(route).status_code==401
    assert client.get(route,headers={"Authorization":"Bearer "+token}).status_code==401
    r=client.get(route,auth=("judge","unique-long-audit-judge-secret"))
    assert r.status_code==200
    assert r.json()["mode"]=="PAYPAL_SANDBOX"
    assert "no-store" in r.headers["Cache-Control"]
