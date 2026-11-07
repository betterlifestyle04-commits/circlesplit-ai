"""Participant invitation portal strict, exact-hash CSP contract.

These tests never use invitation tokens from actual participants, call PayPal,
or contact a live provider. The public HTML must never be cached; its
authorized inline program makes same-origin bearer API calls only.
"""
import base64
import hashlib
import importlib
from pathlib import Path
import re

from fastapi.testclient import TestClient
import pytest

import csp

ROOT = Path(__file__).resolve().parents[1]
AUTH = ("owner", "test-only-owner-password-private")


@pytest.fixture
def hosted(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "private-invitation.sqlite"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.setenv("DEMO_USERNAME", AUTH[0])
    monkeypatch.setenv("DEMO_PASSWORD", AUTH[1])
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as client:
        yield client


def _inline(html):
    return re.findall(r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script\s*>",
                      html, flags=re.IGNORECASE | re.DOTALL)


def _hash(code):
    return "'sha256-" + base64.b64encode(
        hashlib.sha256(code.encode("utf-8")).digest()
    ).decode("ascii") + "'"


def _directives(policy):
    return [item.strip() for item in policy.split(";")]


def test_participant_page_uses_only_exact_authorized_inline_script(hosted):
    response = hosted.get("/participant")
    assert response.status_code == 200
    page = response.text
    assert page == (ROOT / "static" / "participant.html").read_text(encoding="utf-8")
    scripts = _inline(page)
    assert len(scripts) == 1
    policy = response.headers["content-security-policy"]
    assert policy == csp.PUBLIC_PAGE_CSP["/participant"]
    lines = _directives(policy)
    assert "default-src 'none'" in lines
    assert "base-uri 'none'" in lines
    assert "object-src 'none'" in lines
    assert "frame-ancestors 'none'" in lines
    assert "form-action 'none'" in lines
    assert "worker-src 'none'" in lines
    assert "connect-src 'self'" in lines
    assert "img-src 'self' data:" in lines
    directives = [value.split() for value in lines if value.startswith("script-src ")]
    assert len(directives) == 1
    assert directives[0] == ["script-src", "'self'", _hash(scripts[0])]
    assert csp.inline_script_hashes(page) == (_hash(scripts[0]),)
    for forbidden in ("'unsafe-inline'", "'unsafe-eval'", "*",
                      "https:", "http:", "data:", "blob:"):
        assert forbidden not in directives[0]


def test_participant_privacy_headers_and_cache_controls(hosted):
    response = hosted.get("/participant")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, no-store, max-age=0"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert "camera=()" in response.headers["permissions-policy"]
    assert "html" in response.headers["content-type"].lower()
    # The static document contains client code but no invitation data.
    assert 'Private participant approval' in response.text
    assert "<script" in response.text


def test_portal_runs_same_origin_invitation_api_and_calendar_without_script_wildcards(hosted):
    script = _inline(hosted.get("/participant").text)[0]
    assert 'fetch(path,' in script
    assert "/api/participant/calendar.ics" in script
    assert 'URL.createObjectURL' in script
    assert '"Authorization":' in script or "Authorization:" in script
    policy = hosted.get("/participant").headers["content-security-policy"]
    # Connect-src self still permits the participant's separate bearer token
    # on same-origin API requests; javascript execution stays hash-bound.
    assert "connect-src 'self'" in policy
    assert "script-src 'self' 'sha256-" in policy
    assert "connect-src *" not in policy
    assert "script-src 'unsafe-inline'" not in policy


def test_script_modification_is_not_authorized_by_original_policy():
    source = (ROOT / "static" / "participant.html").read_text(encoding="utf-8")
    original = _inline(source)
    changed = _inline(source.replace(
        "<script>", '<script>\nwindow.fakePrivateInvitation = "stolen";', 1
    ))
    assert len(original) == len(changed) == 1
    assert _hash(original[0]) != _hash(changed[0])
    policy = csp.PUBLIC_PAGE_CSP["/participant"]
    assert _hash(original[0]) in policy
    assert _hash(changed[0]) not in policy


def test_portal_script_hash_changes_on_any_whitespace_edit():
    original = (ROOT / "static" / "participant.html").read_text(encoding="utf-8")
    modified = original.replace("<script>", "<script>\n ", 1)
    assert _inline(original)[0] != _inline(modified)[0]
    assert _hash(_inline(modified)[0]) not in csp.PUBLIC_PAGE_CSP["/participant"]


def test_private_invitation_page_disallows_inline_event_handlers():
    page = (ROOT / "static" / "participant.html").read_text(encoding="utf-8")
    assert not re.search(r"\son[a-z]+\s*=", page, flags=re.IGNORECASE)
    assert not re.search(r"<script\b[^>]*\bsrc\s*=", page, flags=re.IGNORECASE)
    assert len(_inline(page)) == 1
    assert "'unsafe-inline'" not in [
        d for d in _directives(csp.PUBLIC_PAGE_CSP["/participant"])
        if d.startswith("script-src")
    ][0]


def test_portal_does_not_make_private_html_source_anonymous(hosted):
    # Only /participant is anonymously accessible; the raw source file
    # remains protected under /static/ and private organizer stays guarded.
    assert hosted.get("/participant").status_code == 200
    assert hosted.get("/static/participant.html").status_code == 401
    assert hosted.get("/workspace").status_code == 401
    assert hosted.get("/api/participant/overview").status_code == 401
    assert hosted.get("/static/participant.html", auth=AUTH).status_code == 200


def test_query_string_does_not_disable_private_page_security_headers(hosted):
    response = hosted.get("/participant?preview=1")
    assert response.status_code == 200
    assert response.headers["content-security-policy"] == csp.PUBLIC_PAGE_CSP["/participant"]
    assert response.headers["cache-control"].startswith("private, no-store")
    assert response.headers["referrer-policy"] == "no-referrer"
