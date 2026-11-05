"""No-show exposure is a read-only, intentionally illustrative sandbox forecast."""
import importlib

import pytest
from fastapi.testclient import TestClient
from attendance_risk import attendance_stress_curve


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "attendance.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def call(client, eid, target="12.00", maximum_absent=5, strategy="equal"):
    return client.post(f"/api/events/{eid}/attendance-risk", json={
        "max_share": target, "maximum_absent": maximum_absent, "strategy": strategy,
    })


def seed(client):
    return client.get("/api/state").json()["events"][0]


def test_equal_splits_are_exact_cent_and_five_missing_people_change_shares(client):
    event = seed(client)
    before = client.get("/api/state").json()
    response = call(client, event["id"])
    assert response.status_code == 200, response.text
    d = response.json()
    assert d["mode"] == "SANDBOX_PLANNING_ONLY"
    assert d["read_only"] is True
    assert d["budget_cents"] == 22000
    assert d["current_people"] == 20
    assert d["first_target_breach_at_absences"] == 2
    assert [p["absent_people"] for p in d["projections"]] == list(range(6))
    assert [p["largest_share_cents"] for p in d["projections"]] == [
        1100, 1158, 1223, 1295, 1375, 1467
    ]
    assert [p["remaining_people"] for p in d["projections"]] == [
        20, 19, 18, 17, 16, 15
    ]
    assert d["projections"][0]["over_target"] is False
    assert d["projections"][2]["over_target"] is True
    assert [p["minimum_replacements_needed"] for p in d["projections"]] == [
        0, 0, 1, 2, 3, 4,
    ]
    assert d["projections"][2]["best_replacement_largest_share_cents"] == 1158
    assert d["projections"][2]["replacement_candidates_tested"] == 2
    assert d["projections"][5]["replacements_feasible"] is True
    assert d["projections"][5]["best_replacement_count"] == 4
    assert client.get("/api/state").json() == before


def test_weighted_absence_selection_is_documented_deterministic_and_uses_real_allocator():
    people = [{"id": 10, "weight": 3},
              {"id": 20, "weight": 2},
              {"id": 30, "weight": 1}]
    d = attendance_stress_curve(10001, people, "weighted", 2, 7000)
    assert d["scenario_rule"] == "retain_highest_weight_remove_next_highest"
    assert d["first_target_breach_at_absences"] == 1
    assert [p["largest_share_cents"] for p in d["projections"]] == [
        5000, 7501, 10001
    ]
    assert [p["smallest_share_cents"] for p in d["projections"]] == [
        1667, 2500, 10001
    ]
    assert [p["largest_share_increase_cents"] for p in d["projections"]] == [
        0, 2501, 5001
    ]
    # Losing the higher-weight member does not imply a new member can cover
    # their old weight. The solver reuses the real allocator, not headcounts.
    assert [p["minimum_replacements_needed"] for p in d["projections"]] == [
        0, 1, 2,
    ]
    assert d["projections"][1]["best_replacement_largest_share_cents"] == 6001
    assert d["projections"][2]["best_replacement_largest_share_cents"] == 6001


def test_one_person_clamps_requested_max_without_empty_roster(client):
    created = client.post("/api/events", json={
        "name": "Solo", "date": "2026-11-12"
    }).json()
    eid = created["id"]
    assert client.post(f"/api/events/{eid}/expenses", json={
        "title": "Space", "amount": "30.00"
    }).status_code == 200
    assert client.post(f"/api/events/{eid}/people", json={
        "name": "Only participant", "weight": 1
    }).status_code == 200
    d = call(client, eid, "20.00", 20).json()
    assert d["tested_maximum_absent"] == 0
    assert len(d["projections"]) == 1
    assert d["first_target_breach_at_absences"] == 0
    assert d["projections"][0]["largest_share_cents"] == 3000
    assert d["projections"][0]["minimum_replacements_needed"] == 1
    assert d["projections"][0]["best_replacement_largest_share_cents"] == 1500


def test_no_recovery_within_fifty_attendees_does_not_claim_affordable(client):
    d = call(client, seed(client)["id"], "0.01", 3).json()
    assert d["read_only"] is True
    for row in d["projections"]:
        assert row["replacements_feasible"] is False
        assert row["minimum_replacements_needed"] is None
        assert row["maximum_replacements_considered"] == 50
        assert row["replacement_candidates_tested"] == 51
        assert row["best_replacement_count"] == 50
        assert row["replacement_gap_cents"] > 0


def test_replacement_search_enforces_two_hundred_person_limit():
    people = [{"id": i, "weight": 1} for i in range(1, 201)]
    d = attendance_stress_curve(10_000, people, "equal", 1, 1)
    full = d["projections"][0]
    assert full["remaining_people"] == 200
    assert full["maximum_replacements_considered"] == 0
    assert full["replacement_candidates_tested"] == 1
    assert full["replacements_feasible"] is False
    assert full["minimum_replacements_needed"] is None
    one_absent = d["projections"][1]
    assert one_absent["maximum_replacements_considered"] == 1
    assert one_absent["replacement_candidates_tested"] == 2
    assert one_absent["replacements_feasible"] is False


def test_never_claims_sandbox_checkout_or_real_rsvp_from_replacement_preview(client):
    eid = seed(client)["id"]
    d = call(client, eid, "12.00", 3).json()
    assert "checkout_url" not in d
    assert "paypal_order" not in d
    assert "invitation" not in d
    assert d["mode"] == "SANDBOX_PLANNING_ONLY"
    assert d["projections"][2]["minimum_replacements_needed"] == 1


def test_empty_event_is_not_a_valid_stress_scenario(client):
    created = client.post("/api/events", json={
        "name": "Empty", "date": "2026-11-12"
    }).json()
    assert call(client, created["id"]).status_code == 422


@pytest.mark.parametrize("change", [
    {"max_share": "0"}, {"max_share": "-1.00"}, {"max_share": "1.234"},
    {"max_share": "NaN"}, {"max_share": "10."}, {"max_share": "100000.01"},
    {"max_share": 10}, {"max_share": True}, {"max_share": "1e3"},
    {"maximum_absent": -1}, {"maximum_absent": 21},
    {"maximum_absent": 0.5}, {"maximum_absent": True},
    {"maximum_absent": "4"}, {"strategy": "bogus"}, {"pay": True},
])
def test_dangerous_or_invalid_inputs_are_rejected(client, change):
    eid = seed(client)["id"]
    body = {"max_share": "12.00", "maximum_absent": 5, "strategy": "equal"}
    body.update(change)
    result = client.post(f"/api/events/{eid}/attendance-risk", json=body)
    assert result.status_code == 422, result.text


def test_preview_never_changes_approvals_payments_or_history(client):
    eid = seed(client)["id"]
    pid = seed(client)["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 200
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code == 200
    import app
    with app.db() as c:
        before_history = c.execute("SELECT COUNT(*) FROM event_history").fetchone()[0]
        before_payments = c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    before = client.get("/api/state").json()
    d = call(client, eid).json()
    assert d["approved_people"] >= 1
    assert d["paid_or_simulated_people"] >= 1
    assert d["read_only"] is True
    assert client.get("/api/state").json() == before
    with app.db() as c:
        assert c.execute("SELECT COUNT(*) FROM event_history").fetchone()[0] == before_history
        assert c.execute("SELECT COUNT(*) FROM payments").fetchone()[0] == before_payments


def test_existing_event_and_hosted_auth_only(client, monkeypatch):
    assert call(client, 999999).status_code == 404
    eid = seed(client)["id"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.setenv("DEMO_PASSWORD", "long-private-shared-test-password")
    assert call(client, eid).status_code == 401
    response = client.post(f"/api/events/{eid}/attendance-risk", json={
        "max_share": "12.00", "maximum_absent": 2, "strategy": "equal",
    }, auth=("judge", "long-private-shared-test-password"))
    assert response.status_code == 200, response.text
    assert "no-store" in response.headers.get("Cache-Control", "")
    assert "PRIVATE-ORDER" not in response.text
