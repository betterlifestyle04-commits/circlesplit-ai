"""Strict CSP regression against actual FastAPI-hosted fictional demo files.

A content hash must exactly match deployed inline JavaScript. Dynamic
user input never becomes an allowed inline program or external request.
No provider traffic or real payment operation occurs.
"""
import base64
import hashlib
import importlib
from pathlib import Path
import re

from fastapi.testclient import TestClient
import pytest

import csp


ROOT=Path(__file__).resolve().parents[1]
AUTH=("owner","this-is-only-the-long-test-password")


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"content-security.sqlite3"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_USERNAME",AUTH[0])
    monkeypatch.setenv("DEMO_PASSWORD",AUTH[1])
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as c:
        yield c


def script_directive(policy):
    parts=[part.strip() for part in policy.split(";")]
    matches=[part for part in parts if part.startswith("script-src ")]
    assert len(matches)==1
    return matches[0].split()


@pytest.mark.parametrize("path,file",[
    ("/","public.html"),
    ("/judge","judge.html"),
])
def test_public_pages_enforce_strict_hash_based_csp(client,path,file):
    response=client.get(path)
    assert response.status_code==200
    html=response.text
    policy=response.headers["Content-Security-Policy"]
    assert response.headers["Cache-Control"]=="public, no-store, max-age=0"
    assert policy==csp.PUBLIC_PAGE_CSP[path]
    assert "default-src 'none'" in policy
    assert "base-uri 'none'" in policy
    assert "object-src 'none'" in policy
    assert "frame-ancestors 'none'" in policy
    assert "form-action 'none'" in policy
    assert "worker-src 'none'" in policy
    assert "style-src 'self' 'unsafe-inline'" in policy
    assert "img-src 'self' data:" in policy

    tokens=script_directive(policy)
    assert tokens[0]=="script-src"
    assert "'self'" in tokens
    for unsafe in ("'unsafe-inline'","'unsafe-eval'","*","https:","http:","data:","blob:"):
        assert unsafe not in tokens
    assert policy.endswith("worker-src 'none'")

    # Independent hash derivation, not just trusting the csp.py function.
    snippets=re.findall(r"<script>([\s\S]*?)</script>",html)
    assert len(snippets)==(1 if path=="/" else 0)
    hashed=[
        "'sha256-"+base64.b64encode(hashlib.sha256(code.encode("utf-8")).digest()).decode("ascii")+"'"
        for code in snippets
    ]
    assert [value for value in tokens if value.startswith("'sha256-")]==hashed
    assert html== (ROOT/"static"/file).read_text(encoding="utf-8")


def test_browser_only_public_demo_cannot_contact_server_or_third_party(client):
    response=client.get("/")
    p=response.headers["Content-Security-Policy"]
    assert "connect-src 'none'" in p
    assert "connect-src 'self'" not in p
    assert "frame-ancestors 'none'" in p
    for external in ("https://cdn.", "https://fonts.", "unsafe-eval"):
        assert external not in p
    assert "/static/public_portability.js" in response.text
    assert "/static/public_scenarios.js" in response.text
    assert "/static/public_recovery.js" in response.text


def test_public_judge_can_still_fetch_same_origin_health(client):
    response=client.get("/judge")
    policy=response.headers["Content-Security-Policy"]
    assert "connect-src 'self'" in policy
    assert "connect-src 'none'" not in policy
    assert "<script src=\"/static/judge_walkthrough.js\"></script>" in response.text
    assert client.get("/health").status_code==200


def test_unknown_inline_javascript_is_not_allowed_by_existing_public_policy():
    current=(ROOT/"static"/"public.html").read_text(encoding="utf-8")
    malicious=current.replace(
        "<script>",
        "<script>\nwindow.untrustedInjectedScript = true;\n",
        1
    )
    original=csp.inline_script_hashes(current)
    changed=csp.inline_script_hashes(malicious)
    assert len(original)==len(changed)==1
    assert original!=changed
    allowed=script_directive(csp.PUBLIC_PAGE_CSP["/"])
    assert original[0] in allowed
    assert changed[0] not in allowed
    assert "window.untrustedInjectedScript" not in current


def test_no_inline_event_handlers_are_allowed_on_public_pages():
    for file in ("public.html","judge.html"):
        src=(ROOT/"static"/file).read_text(encoding="utf-8")
        # These pages do not use inline onclick/onload/onerror handlers.
        assert not re.search(r"\s+on(?:click|load|error|submit|change|input)\s*=",src,re.I)
        policy=csp.page_csp(src,allow_health=file=="judge.html")
        assert "'unsafe-inline'" not in script_directive(policy)


def test_error_responses_do_not_open_a_public_script_bypass(client):
    assert client.get("/workspace").status_code==401
    assert client.get("/static/index.html").status_code==401
    assert client.get("/static/public_scenarios.js").status_code==200
    owner=client.get("/workspace",auth=AUTH)
    assert owner.status_code==200
    assert "Content-Security-Policy" not in owner.headers
    # The organizer's historical inline handlers require a separate
    # migration; do not falsely claim that they run under this CSP.


def test_csp_is_not_enabled_through_an_arbitrary_query_or_static_path(client):
    root=client.get("/?foo=bar")
    guide=client.get("/judge?foo=bar")
    assert root.headers["Content-Security-Policy"]==csp.PUBLIC_PAGE_CSP["/"]
    assert guide.headers["Content-Security-Policy"]==csp.PUBLIC_PAGE_CSP["/judge"]
    for path in ("/static/public.html","/static/judge.html"):
        response=client.get(path)
        assert response.status_code==401
        assert "Content-Security-Policy" not in response.headers


def test_csp_builder_rejects_nonstrings_and_keeps_directives_fixed():
    with pytest.raises(ValueError):
        csp.inline_script_hashes(None)
    for text in (
        "<script>alert(1)</script>",
        '<script src="/static/known.js"></script>',
        "<p>no scripts</p>",
    ):
        policy=csp.page_csp(text)
        assert "default-src 'none'" in policy
        assert "form-action 'none'" in policy
        assert "connect-src 'none'" in policy
        assert "'unsafe-inline'" not in script_directive(policy)
