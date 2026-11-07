"""Owner-only evaluation of expiring hackathon judge access.

No passwords, usernames, hashes, provider configuration, or secret values
are returned. This check examines deployment configuration, not login
success or actual judge usability. Judges remain blocked from PayPal
order creation, capture, and reconciliation by separate middleware.
"""
from datetime import datetime, timezone
import os

JUDGING_END_UTC = datetime(2026, 12, 15, 16, 0, tzinfo=timezone.utc)


def _parse_expiry(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return None
        return parsed.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None


def assess_judge_access(config=None, *, now=None):
    """Fail closed on invalid, expired, weak, or overlapping judge access.

    "ready_for_judging" means only that configured credentials appear to
    cover the public Devpost judging window, NOT that a login works.
    Never place raw environment input in return values.
    """
    config = os.environ if config is None else config
    now = datetime.now(timezone.utc) if now is None else now
    if now.tzinfo is None:
        raise ValueError("Current time must be timezone aware")
    now = now.astimezone(timezone.utc)

    enabled = config.get("JUDGE_ACCESS_ENABLED") == "1"
    judge_name = config.get("JUDGE_USERNAME") or ""
    judge_pass = config.get("JUDGE_PASSWORD") or ""
    owner_name = config.get("DEMO_USERNAME") or ""
    owner_pass = config.get("DEMO_PASSWORD") or ""
    expiry = _parse_expiry(config.get("JUDGE_ACCESS_EXPIRES_AT"))

    problems = []
    if not enabled:
        problems.append("judge_login_disabled")
    if not isinstance(judge_name, str) or not judge_name.strip():
        problems.append("judge_username_missing")
    elif judge_name == owner_name:
        problems.append("judge_username_matches_owner")
    if not isinstance(judge_pass, str) or len(judge_pass) < 18:
        problems.append("judge_password_missing_or_short")
    elif judge_pass == owner_pass:
        problems.append("judge_password_matches_owner")
    if expiry is None:
        problems.append("judge_expiry_missing_or_invalid")
    elif expiry <= now:
        problems.append("judge_login_expired")
    elif expiry < JUDGING_END_UTC:
        problems.append("judge_login_expires_during_judging")
    if now >= JUDGING_END_UTC:
        problems.append("judging_window_ended")

    return {
        "mode": "READ_ONLY_JUDGE_CONFIGURATION_CHECK",
        "ready_for_judging": not problems,
        "problems": problems,
        "judging_ends_at_utc": JUDGING_END_UTC.isoformat().replace("+00:00", "Z"),
        "sandbox_actions_allowed_for_judges": False,
        "provider_calls_performed": False,
        "notice": (
            "A ready configuration is not proof that a real judge login works. "
            "Test a separate judge credential in an incognito browser. "
            "Judge access does not permit PayPal Sandbox order creation, "
            "capture or reconciliation; only the organizer can do those actions. "
            "Never send judge passwords to a public page or repository."
        )
    }
