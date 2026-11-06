"""Verify public guest-page JavaScript is available without opening organizer assets.

No provider interaction, no customer data, and no real payments.
"""
import importlib

import pytest
from fastapi.testclient import TestClient
from security import PUBLIC_DEMO_SCRIPT_PATHS, public_demo_script


PUBLIC_ASSETS={
    "/static/public_recovery.js":"CircleSplitPublicRecovery",
    "/static/public_portability.js":"CircleSplitPublicPortability",
    "/static/judge_walkthrough.js":None,
}


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"public-assets.sqlite3"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_USERNAME","owner")
    monkeypatch.setenv("DEMO_PASSWORD","this-is-a-private-test-owner-password")
    monkeypatch.setenv("PUBLIC_BASE_URL","https://circlesplit-ai-demo.onrender.com")
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def test_public_js_allowlist_exact_and_methods_restricted():
    assert PUBLIC_DEMO_SCRIPT_PATHS==set(PUBLIC_ASSETS)
    for path in PUBLIC_ASSETS:
        assert public_demo_script("GET",path)
        assert public_demo_script("HEAD",path)
        for method in ["POST","PUT","PATCH","DELETE","OPTIONS"]:
            assert not public_demo_script(method,path)
    for path in [
        "/static/index.html",
        "/static/public.html",
        "/static/participant.html",
        "/static/recovery_triage.js",
        "/static/judge_walkthrough.js.map",
        "/static/public_recovery.js/extra",
        "/static/public_portability.js.backup",
        "/static/public_portability.js/",
        "/static/public_recovery.js.extra",
    ]:
        assert not public_demo_script("GET",path)


@pytest.mark.parametrize("path",list(PUBLIC_ASSETS))
def test_public_browser_assets_are_retrievable_without_basic_auth(client,path):
    r=client.get(path)
    assert r.status_code==200,(path,r.text[:150])
    assert "javascript" in r.headers["content-type"].lower()
    assert r.headers["cache-control"]=="public, no-store, max-age=0"
    assert r.headers["x-content-type-options"]=="nosniff"
    assert r.headers["x-frame-options"]=="DENY"
    assert r.headers["referrer-policy"]=="no-referrer"
    assert len(r.content)>200
    if PUBLIC_ASSETS[path]:
        assert PUBLIC_ASSETS[path] in r.text
    head=client.head(path)
    assert head.status_code==200
    assert head.content==b""
    assert "no-store" in head.headers["cache-control"]


def test_public_pages_reference_only_approved_public_scripts(client):
    root=client.get("/")
    guide=client.get("/judge")
    assert root.status_code==guide.status_code==200
    assert '<script src="/static/public_recovery.js"></script>' in root.text
    assert '<script src="/static/public_portability.js"></script>' in root.text
    assert '<script src="/static/judge_walkthrough.js"></script>' in guide.text
    assert "Download backup" in root.text
    assert "Restore backup" in root.text


@pytest.mark.parametrize("path",[
    "/static/index.html",
    "/static/public.html",
    "/static/participant.html",
    "/static/recovery_triage.js",
    "/static/ledger_audit.js",
    "/static/insights.js",
    "/static/public_recovery.js.backup",
])
def test_workspace_assets_and_unknown_files_still_require_basic_auth(client,path):
    response=client.get(path)
    assert response.status_code==401,(path,response.status_code)
    assert "no-store" in response.headers["cache-control"]
    assert "Basic" in response.headers["WWW-Authenticate"]
    assert "Protected testing workspace" in response.text


def test_public_script_allowlist_does_not_weaken_organizer_api_or_mutations(client):
    for path in ["/api/state","/api/paypal/recovery","/api/judge-readiness"]:
        assert client.get(path).status_code==401
    assert client.post("/api/events",json={
        "name":"Anonymous client must not create events","date":"2026-11-06"
    }).status_code==401
    assert client.post("/api/paypal/orders/1/1").status_code==401
    for path in PUBLIC_ASSETS:
        assert client.post(path).status_code==401
        assert client.get(path+"/extra").status_code==401


def test_authenticated_owner_still_reads_protected_static_and_same_public_js(client):
    auth=("owner","this-is-a-private-test-owner-password")
    assert client.get("/static/index.html",auth=auth).status_code==200
    assert client.get("/api/state",auth=auth).status_code==200
    for path in PUBLIC_ASSETS:
        public=client.get(path)
        private=client.get(path,auth=auth)
        assert public.status_code==private.status_code==200
        assert public.content==private.content
