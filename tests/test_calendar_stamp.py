"""Stable privacy-minimal calendar stamps for the same agenda revision."""
import importlib
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "calendar-stamp.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def expected_stamp(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(
        timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def test_organizer_and_invitee_share_one_persisted_stamp(client):
    import app
    event=client.get("/api/state").json()["events"][0]
    eid,pid=event["id"],event["people"][0]["id"]
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    saved=client.post(f"/api/events/{eid}/agenda",json={
        "start_time":"10:00","end_time":"11:00","title":"Group warmup",
        "note":"Bring shoes"
    })
    assert saved.status_code == 200, saved.text
    with app.db() as conn:
        timestamp=conn.execute("SELECT agenda_changed_at FROM events WHERE id=?",
                               (eid,)).fetchone()["agenda_changed_at"]
    assert timestamp is not None
    one=client.get(f"/api/events/{eid}/calendar.ics")
    two=client.get("/api/participant/calendar.ics",
                   headers={"Authorization":f"Bearer {token}"})
    three=client.get(f"/api/events/{eid}/calendar.ics")
    assert one.status_code == two.status_code == three.status_code == 200
    assert one.content == two.content == three.content
    assert f"DTSTAMP:{expected_stamp(timestamp)}" in one.text
    assert "SEQUENCE:1" in one.text


def test_legacy_agenda_without_timestamp_uses_stable_creation_time(client):
    import app
    event=client.get("/api/state").json()["events"][0]
    eid=event["id"]
    assert client.post(f"/api/events/{eid}/agenda",json={
        "start_time":"15:00","end_time":"16:00","title":"Volleyball",
    }).status_code == 200
    with app.db() as conn:
        conn.execute("UPDATE events SET agenda_changed_at=NULL WHERE id=?", (eid,))
        created=conn.execute("SELECT created FROM events WHERE id=?",
                             (eid,)).fetchone()["created"]
    first=client.get(f"/api/events/{eid}/calendar.ics")
    second=client.get(f"/api/events/{eid}/calendar.ics")
    assert first.status_code == 200
    assert first.content == second.content
    assert f"DTSTAMP:{expected_stamp(created)}" in first.text


def test_invalid_stored_timestamp_fails_closed_without_payment_side_effects(client):
    import app
    e=client.get("/api/state").json()["events"][0]
    eid=e["id"]
    assert client.post(f"/api/events/{eid}/agenda",json={
        "start_time":"17:00","end_time":"18:00","title":"Group game"
    }).status_code == 200
    previous=client.get("/api/state").json()
    with app.db() as conn:
        conn.execute("UPDATE events SET agenda_changed_at=? WHERE id=?",
                     ("not-a-date",eid))
    denied=client.get(f"/api/events/{eid}/calendar.ics")
    assert denied.status_code == 409
    assert "calendar" in denied.json()["detail"].lower() or "format" in denied.json()["detail"].lower()
    assert client.get("/api/state").json()["events"][0]["sandbox_cents"] == 0
