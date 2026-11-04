"""Storage identity and optional persistent-mount checkout safety tests.

These tests never contact real PayPal or claim actual data durability.
"""
import importlib
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import paypal
import storage_readiness as guard


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "ledger.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("CIRCLESPLIT_PERSISTENT_MOUNT", raising=False)
    monkeypatch.delenv("CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def test_ephemeral_render_status_never_exposes_real_db_path(tmp_path):
    location = tmp_path / "private" / "actual.sqlite3"
    data = guard.storage_readiness(location,{
        "RENDER":"true", "CIRCLESPLIT_HOSTED":"1",
        "CIRCLESPLIT_PERSISTENT_MOUNT":str(tmp_path / "not-mounted"),
    })
    assert data["storage"] == "ephemeral-sqlite"
    assert data["persistent_mount_verified"] is False
    assert data["sandbox_checkout_allowed"] is True  # Existing free demo still works.
    assert str(tmp_path) not in str(data)
    assert "restart" in data["notice"]


def test_opt_in_gate_fails_closed_without_verified_mount(tmp_path):
    path = tmp_path / "db.sqlite3"
    result = guard.storage_readiness(path,{
        "RENDER":"true",
        "CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB":"1",
        "CIRCLESPLIT_PERSISTENT_MOUNT":str(tmp_path),
    })
    assert result["sandbox_checkout_allowed"] is False
    assert result["checkout_requires_persistent_mount"] is True
    assert result["persistent_mount_verified"] is False


def test_actual_mount_verification_excludes_root_outsiders_and_symlinks(tmp_path, monkeypatch):
    mount = tmp_path / "disk"
    mount.mkdir()
    outsider = tmp_path / "disk-like" / "ledger.sqlite3"
    monkeypatch.setattr(guard.os.path, "ismount", lambda p:p == str(mount))
    inside = mount / "ledger.sqlite3"
    assert guard.mounted_database(inside, str(mount)) is True
    assert guard.mounted_database(outsider, str(mount)) is False
    assert guard.mounted_database(inside, "/") is False
    assert guard.mounted_database(inside, "") is False
    assert guard.mounted_database("relative.sqlite3", str(mount)) is False
    assert guard.mounted_database(inside, "relative") is False
    assert guard.mounted_database(mount, str(mount)) is False
    escape = mount / "escape"
    escape.symlink_to(tmp_path, target_is_directory=True)
    assert guard.mounted_database(escape / "ledger.sqlite3", str(mount)) is False


def test_fake_mount_env_alone_never_proves_durability(tmp_path):
    mount = tmp_path / "folder"
    mount.mkdir()
    data = guard.storage_readiness(mount / "ledger.sqlite3",{
        "RENDER":"true",
        "CIRCLESPLIT_PERSISTENT_MOUNT":str(mount),
        "CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB":"1"
    })
    assert not data["persistent_mount_verified"]
    assert not data["sandbox_checkout_allowed"]


def test_real_mount_path_simulation_allows_strict_checkout(tmp_path,monkeypatch):
    mount = tmp_path / "volume"
    mount.mkdir()
    monkeypatch.setattr(guard.os.path,"ismount",lambda p:p == str(mount))
    ready=guard.storage_readiness(mount / "ledger.sqlite3",{
        "RENDER":"true",
        "CIRCLESPLIT_PERSISTENT_MOUNT":str(mount),
        "CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB":"1",
    })
    assert ready["storage"]=="mounted-sqlite"
    assert ready["persistent_mount_verified"] is True
    assert ready["sandbox_checkout_allowed"] is True
    assert "backups" in ready["notice"]


def test_storage_epoch_is_stable_until_physical_db_reset(client):
    import app
    first=client.get("/api/judge-readiness").json()
    assert first["storage"]=="local-sqlite-unverified"
    assert len(first["storage_epoch"])==12
    assert first["storage_created_at"]
    assert first["persistent_mount_verified"] is False
    with app.db() as c:
        before=c.execute("SELECT incarnation_id FROM storage_identity WHERE id=1").fetchone()[0]
    app.initialize()
    second=client.get("/api/judge-readiness").json()
    assert second["storage_epoch"]==first["storage_epoch"]
    with app.db() as c:
        after=c.execute("SELECT incarnation_id FROM storage_identity WHERE id=1").fetchone()[0]
    assert before==after
    # Simulate losing the ephemeral SQLite file, never an external provider reset.
    app.DB.unlink()
    app.initialize()
    third=client.get("/api/judge-readiness").json()
    assert third["storage_epoch"]!=first["storage_epoch"]


def test_storage_readiness_private_and_never_exposes_secrets(client,monkeypatch):
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_USERNAME","organizer")
    monkeypatch.setenv("DEMO_PASSWORD","secure-test-only-demo-password")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET","secret-must-not-appear")
    monkeypatch.setenv("GEMINI_API_KEY","private-gemini-secret")
    assert client.get("/api/judge-readiness").status_code==401
    response=client.get("/api/judge-readiness",
        auth=("organizer","secure-test-only-demo-password"))
    assert response.status_code==200,response.text
    data=response.json()
    assert data["storage"]=="ephemeral-sqlite"
    assert data["persistent_mount_verified"] is False
    assert len(data["storage_epoch"])==12
    assert "secret-must-not-appear" not in response.text
    assert "private-gemini-secret" not in response.text
    assert str(Path(__file__).parent) not in response.text
    assert "no-store" in response.headers["Cache-Control"]
    assert client.get("/health").status_code==200
    assert "storage_epoch" not in client.get("/health").text


def test_strict_gate_prevents_new_order_before_local_or_provider_mutation(client,monkeypatch):
    event=client.get("/api/state").json()["events"][0]
    eid=event["id"];pid=event["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    calls=[]
    monkeypatch.setattr(paypal,"configured",lambda:True)
    async def forbidden(*args):
        calls.append(args)
        raise AssertionError("PayPal must never be contacted")
    monkeypatch.setattr(paypal,"order",forbidden)
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","0")
    monkeypatch.setenv("CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB","1")
    denied=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert denied.status_code==503,denied.text
    assert "persistent SQLite mount not verified" in denied.json()["detail"]
    assert calls==[]
    recovery=client.get("/api/paypal/recovery").json()
    assert recovery["total_records"]==0
    assert client.get("/api/state").json()["events"][0]["people"][0]["approved"]==1
    assert client.post("/api/paypal/order-status/UNKNOWN-ORDER-001").status_code==404


def test_existing_checkout_recovery_stays_available_when_gate_turns_on(client,monkeypatch):
    event=client.get("/api/state").json()["events"][0]
    eid=event["id"];pid=event["people"][0]["id"]
    amount=event["people"][0]["share_cents"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    async def new_order(*args):
        return {"id":"TEST-DURABLE-GATE-ORDER",
                "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"}
    monkeypatch.setattr(paypal,"order",new_order)
    created=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert created.status_code==200,created.text
    monkeypatch.setenv("CIRCLESPLIT_CHECKOUT_REQUIRES_DURABLE_DB","1")
    async def existing_capture(*args):
        return {"purchase_units":[{"payments":{"captures":[{
            "id":"TEST-DURABLE-GATE-CAPTURE","status":"COMPLETED",
            "amount":{"currency_code":"USD","value":f"{amount/100:.2f}"},
        }]}}]}
    monkeypatch.setattr(paypal,"capture",existing_capture)
    settled=client.post("/api/paypal/capture",json={"order_id":"TEST-DURABLE-GATE-ORDER"})
    assert settled.status_code==200,settled.text
    assert client.get("/api/state").json()["events"][0]["sandbox_cents"]==amount
    assert client.get("/api/paypal/recovery").json()["summary"]["completed"]==1
