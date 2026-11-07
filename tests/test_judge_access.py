"""Owner-only judge expiry preflight for the official December judging window.

Does not use PayPal, Gemini, a live login, or actual secrets.
"""
from datetime import datetime, timedelta, timezone
import importlib

import pytest
from fastapi.testclient import TestClient

from judge_access import JUDGING_END_UTC, assess_judge_access

OWNER = ("owner-review", "owner-long-private-password-for-test")
JUDGE = ("separate-judge", "different-long-private-password-test")
NOW = datetime(2026, 11, 7, 22, 45, tzinfo=timezone.utc)
FUTURE = "2026-12-20T00:00:00+00:00"


def config(**overrides):
    source = {
        "DEMO_USERNAME": OWNER[0],
        "DEMO_PASSWORD": OWNER[1],
        "JUDGE_ACCESS_ENABLED": "1",
        "JUDGE_USERNAME": JUDGE[0],
        "JUDGE_PASSWORD": JUDGE[1],
        "JUDGE_ACCESS_EXPIRES_AT": FUTURE,
    }
    source.update(overrides)
    return source


def test_official_judging_end_is_utc_and_safely_after_submission():
    assert JUDGING_END_UTC == datetime(2026, 12, 15, 16, 0, tzinfo=timezone.utc)
    result = assess_judge_access(config(), now=NOW)
    assert result["ready_for_judging"] is True
    assert result["problems"] == []
    assert result["judging_ends_at_utc"] == "2026-12-15T16:00:00Z"
    assert result["mode"] == "READ_ONLY_JUDGE_CONFIGURATION_CHECK"
    assert result["sandbox_actions_allowed_for_judges"] is False
    assert result["provider_calls_performed"] is False
    assert "not proof" in result["notice"].lower()


@pytest.mark.parametrize("change,reason", [
    ({"JUDGE_ACCESS_ENABLED": "0"}, "judge_login_disabled"),
    ({"JUDGE_ACCESS_ENABLED": "yes"}, "judge_login_disabled"),
    ({"JUDGE_USERNAME": ""}, "judge_username_missing"),
    ({"JUDGE_USERNAME": "   "}, "judge_username_missing"),
    ({"JUDGE_USERNAME": OWNER[0]}, "judge_username_matches_owner"),
    ({"JUDGE_PASSWORD": ""}, "judge_password_missing_or_short"),
    ({"JUDGE_PASSWORD": "short"}, "judge_password_missing_or_short"),
    ({"JUDGE_PASSWORD": OWNER[1]}, "judge_password_matches_owner"),
    ({"JUDGE_ACCESS_EXPIRES_AT": ""}, "judge_expiry_missing_or_invalid"),
    ({"JUDGE_ACCESS_EXPIRES_AT": "2026-12-20"}, "judge_expiry_missing_or_invalid"),
    ({"JUDGE_ACCESS_EXPIRES_AT": "not-a-date"}, "judge_expiry_missing_or_invalid"),
    ({"JUDGE_ACCESS_EXPIRES_AT": "2026-11-01T00:00:00+00:00"}, "judge_login_expired"),
    ({"JUDGE_ACCESS_EXPIRES_AT": "2026-12-15T15:59:59Z"}, "judge_login_expires_during_judging"),
])
def test_invalid_config_fails_closed_with_stable_nonsensitive_reason(change, reason):
    report = assess_judge_access(config(**change), now=NOW)
    assert report["ready_for_judging"] is False
    assert reason in report["problems"]
    assert report["provider_calls_performed"] is False
    data = str(report)
    for value in (OWNER[0], OWNER[1], JUDGE[0], JUDGE[1], "JUDGE_PASSWORD", "DEMO_PASSWORD"):
        assert value not in data


def test_judging_end_exact_expiry_accepted_and_timezones_normalized():
    cutoff = "2026-12-15T17:00:00+01:00"
    report = assess_judge_access(config(JUDGE_ACCESS_EXPIRES_AT=cutoff), now=NOW)
    assert report["ready_for_judging"] is True
    # The result never reveals the raw deployment variable.
    assert cutoff not in str(report)
    report = assess_judge_access(
        config(JUDGE_ACCESS_EXPIRES_AT="2026-12-15T16:00:01Z"), now=NOW
    )
    assert report["ready_for_judging"] is True


def test_after_judging_window_is_not_marked_ready():
    report = assess_judge_access(
        config(JUDGE_ACCESS_EXPIRES_AT="2027-06-01T00:00:00Z"),
        now=JUDGING_END_UTC + timedelta(days=1),
    )
    assert report["ready_for_judging"] is False
    assert "judging_window_ended" in report["problems"]


def test_naive_now_is_rejected():
    with pytest.raises(ValueError, match="timezone aware"):
        assess_judge_access(config(), now=datetime(2026, 11, 7))


@pytest.fixture
def hosted(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "judge-access.sqlite"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.setenv("DEMO_USERNAME", OWNER[0])
    monkeypatch.setenv("DEMO_PASSWORD", OWNER[1])
    monkeypatch.setenv("JUDGE_ACCESS_ENABLED", "1")
    monkeypatch.setenv("JUDGE_USERNAME", JUDGE[0])
    monkeypatch.setenv("JUDGE_PASSWORD", JUDGE[1])
    monkeypatch.setenv("JUDGE_ACCESS_EXPIRES_AT", FUTURE)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as test_client:
        yield test_client


def test_owner_only_route_reports_ready_state_without_exposing_credentials(hosted):
    result = hosted.get("/api/judge-access-readiness", auth=OWNER)
    assert result.status_code == 200
    data = result.json()
    assert data["mode"] == "READ_ONLY_JUDGE_CONFIGURATION_CHECK"
    assert data["ready_for_judging"] is True
    assert data["sandbox_actions_allowed_for_judges"] is False
    assert data["provider_calls_performed"] is False
    assert "no-store" in result.headers["cache-control"].lower()
    for text in (OWNER[0], OWNER[1], JUDGE[0], JUDGE[1]):
        assert text not in result.text
    assert set(data) == {
        "mode", "ready_for_judging", "problems", "judging_ends_at_utc",
        "sandbox_actions_allowed_for_judges", "provider_calls_performed", "notice"
    }


def test_judge_and_anonymous_cannot_inspect_owner_access_configuration(hosted):
    judge = hosted.get("/api/judge-access-readiness", auth=JUDGE)
    assert judge.status_code == 403
    assert "Organizer credentials required" in judge.text
    assert "no-store" in judge.headers["cache-control"].lower()
    anonymous = hosted.get("/api/judge-access-readiness")
    assert anonymous.status_code == 401
    assert "Basic" in anonymous.headers["www-authenticate"]
    assert hosted.get("/api/state", auth=JUDGE).json()["sandbox_order_actions_allowed"] is False


def test_route_detects_expired_judging_access_without_requesting_secrets(hosted, monkeypatch):
    monkeypatch.setenv("JUDGE_ACCESS_EXPIRES_AT", "2026-11-05T00:00:00Z")
    result = hosted.get("/api/judge-access-readiness", auth=OWNER)
    assert result.status_code == 200
    assert result.json()["ready_for_judging"] is False
    assert "judge_login_expired" in result.json()["problems"]
    assert hosted.get("/workspace", auth=JUDGE).status_code == 401
    assert hosted.get("/workspace", auth=OWNER).status_code == 200


def test_no_provider_calls_or_payment_rows_from_access_probe(hosted, monkeypatch):
    import app
    import paypal

    async def forbidden(*_args, **_kwargs):
        raise AssertionError("Judge access check must never call a provider")
    monkeypatch.setattr(paypal, "details", forbidden)
    monkeypatch.setattr(paypal, "capture", forbidden)
    monkeypatch.setattr(paypal, "order", forbidden)

    with app.db() as conn:
        before = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    for _ in range(3):
        assert hosted.get("/api/judge-access-readiness", auth=OWNER).status_code == 200
    with app.db() as conn:
        after = conn.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    assert before == after
