"""Read-only, aggregate Sandbox recovery risk across all local ledger rows."""
import importlib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
import paypal


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "recovery-risk.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as test:
        yield test


def add_payment(c, eid, pid, n, status, order, capture, created, cents=1100):
    c.execute(
        """INSERT INTO payments(event_id,person_id,amount_cents,request_id,
           capture_key,status,order_id,capture_id,created)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (eid, pid, cents, f"triage-key-{n}", f"triage-capture-key-{n}",
         status, order, capture, created),
    )


def test_empty_ledger_reports_zero_without_contacting_paypal(client, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Read-only risk assessment must not contact PayPal")
    monkeypatch.setattr(paypal, "details", forbidden)
    monkeypatch.setattr(paypal, "capture", forbidden)
    risk = client.get("/api/paypal/recovery?limit=1").json()["risk"]
    assert risk["mode"] == "PAYPAL_SANDBOX"
    assert risk["source"] == "current_local_sqlite_only"
    assert risk["status"] == "no_local_unresolved_records"
    assert risk["total_records"] == risk["attention_count"] == 0
    assert risk["priority_review_count"] == 0
    assert risk["older_than_60_minutes"] == 0
    assert risk["unverified_request_face_value_cents"] == 0
    assert all(n == 0 for n in risk["categories"].values())


def test_all_record_triage_distinguishes_outcomes_age_and_face_value(client, monkeypatch):
    import app
    e = client.get("/api/state").json()["events"][0]
    eid, pid = e["id"], e["people"][0]["id"]
    current = datetime.now(timezone.utc)
    recent = current.isoformat()
    old = (current-timedelta(minutes=90)).isoformat()
    older = (current-timedelta(minutes=180)).isoformat()
    with app.db() as c:
        add_payment(c,eid,pid,1,"creating",None,None,old)
        add_payment(c,eid,pid,2,"capturing","TEST-SBX-2",None,older)
        add_payment(c,eid,pid,3,"created","TEST-SBX-3",None,recent)
        add_payment(c,eid,pid,4,"completed","TEST-SBX-4","TEST-CAPTURE-4",recent)
        add_payment(c,eid,pid,5,"completed","TEST-SBX-5",None,recent)
        add_payment(c,eid,pid,6,"unrecognized","TEST-SBX-6",None,recent)
        add_payment(c,eid,pid,7,"created","TEST-SBX-7",None,"invalid timestamp")
        add_payment(c,987654,876543,8,"created","TEST-SBX-8",None,recent)
        count_before=c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    async def forbidden(*args, **kwargs):
        raise AssertionError("No upstream request allowed")
    monkeypatch.setattr(paypal, "details", forbidden)
    monkeypatch.setattr(paypal, "capture", forbidden)
    state_before = client.get("/api/state").json()
    top = client.get("/api/paypal/recovery?limit=1&offset=0").json()
    bottom = client.get("/api/paypal/recovery?limit=1&offset=7").json()
    r=top["risk"]
    assert bottom["risk"] == r
    assert r["status"] == "needs_manual_review"
    assert r["total_records"] == count_before == 8
    assert r["attention_count"] == 7
    assert r["priority_review_count"] == 5
    assert r["older_than_60_minutes"] == 2
    assert r["unparseable_created_timestamps"] == 1
    assert r["unverified_request_face_value_cents"] == 7700
    assert r["categories"] == {
        "inconsistent_local_record":3,
        "unknown_order_creation":1,
        "uncertain_capture_attempt":1,
        "awaiting_provider_confirmation":2,
        "locally_completed":1,
    }
    assert "TEST-SBX" not in str(r)
    assert "triage-key" not in str(r)
    assert "876543" not in str(r)
    assert client.get("/api/state").json() == state_before
    with app.db() as c:
        assert c.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == count_before


def test_pending_only_is_not_mislabelled_verified_or_failed(client):
    import app
    e = client.get("/api/state").json()["events"][0]
    with app.db() as c:
        add_payment(c,e["id"],e["people"][0]["id"],1,"created",
                    "TEST-SBX-CREATED-1",None,datetime.now(timezone.utc).isoformat())
    r=client.get("/api/paypal/recovery").json()["risk"]
    assert r["status"] == "pending_provider_confirmation"
    assert r["priority_review_count"] == 0
    assert r["attention_count"] == 1
    assert r["categories"]["awaiting_provider_confirmation"] == 1
    assert r["unverified_request_face_value_cents"] == 1100


def test_malformed_link_or_capture_is_local_inconsistency_not_success(client):
    import app
    e=client.get("/api/state").json()["events"][0]
    now=datetime.now(timezone.utc).isoformat()
    with app.db() as c:
        add_payment(c,e["id"],e["people"][0]["id"],1,
                    "created","TEST-SBX-PENDING","GHOST-CAPTURE",now)
        add_payment(c,e["id"],e["people"][0]["id"],2,
                    "completed",None,"GHOST-CAPTURE-2",now)
        add_payment(c,e["id"],e["people"][0]["id"],3,
                    "capturing",None,None,now)
    risk=client.get("/api/paypal/recovery").json()["risk"]
    assert risk["categories"]["inconsistent_local_record"] == 3
    assert risk["categories"]["locally_completed"] == 0
    assert risk["priority_review_count"] == 3
    assert risk["unverified_request_face_value_cents"] == 3300


def test_hosted_recovery_triage_requires_credentials_and_is_private(client, monkeypatch):
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","long-private-sandbox-risk-password")
    assert client.get("/api/paypal/recovery").status_code == 401
    result=client.get("/api/paypal/recovery",
                      auth=("judge","long-private-sandbox-risk-password"))
    assert result.status_code == 200, result.text
    assert "no-store" in result.headers["Cache-Control"]
    assert "risk" in result.json()
    assert client.get("/health").status_code == 200
    assert "risk" not in client.get("/health").text
