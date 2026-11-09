"""PayPal Sandbox upstream JSON and callback validation: no real provider traffic.

Malformed provider replies must result in a controlled 4xx/5xx and must
not register a payment, leak a token, or redirect outside the trusted host.
"""
import asyncio
import importlib
from urllib.parse import urlsplit

import httpx
import paypal
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

OWNER = ("demo-owner", "owner-demo-password-private-and-long")


class ProviderResponse:
    def __init__(self, payload):
        self.payload = payload
    def raise_for_status(self):
        return None
    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


def fake_client(monkeypatch, *, oauth=None, response=None):
    calls = []
    class FakeHttpxClient:
        def __init__(self, *args, **kwargs):
            calls.append(("client", kwargs))
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return False
        async def post(self, url, **kwargs):
            calls.append(("token", url, kwargs))
            return ProviderResponse(oauth)
        async def request(self, method, url, **kwargs):
            calls.append(("api", method, url, kwargs))
            return ProviderResponse(response)
    monkeypatch.setattr(paypal.httpx, "AsyncClient", FakeHttpxClient)
    return calls


@pytest.mark.parametrize("payload", [
    None, [], ["secret"], "", "not-a-dict", 7,
    {}, {"access_token":None}, {"access_token":""},
    {"access_token":123}, {"access_token":[]},
    {"access_token":"abc\r\nAuthorization: Bearer leaked"},
    {"access_token":"ABC DEF"}, {"access_token":"ö-secret"},
    {"access_token":"A"*4097}, ValueError("bad provider json")
])
def test_invalid_oauth_payload_fails_closed_with_no_bearer_or_network_followup(
    monkeypatch,payload
):
    monkeypatch.setenv("PAYPAL_CLIENT_ID", "test-owner")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET", "never-log-this-secret")
    calls=fake_client(monkeypatch,oauth=payload)
    with pytest.raises(HTTPException) as error:
        asyncio.run(paypal.api("POST","/v2/checkout/orders",{"test":True}))
    assert error.value.status_code==502
    assert error.value.detail=="PayPal sandbox authentication failed"
    assert not any(item[0]=="api" for item in calls)
    assert "never-log-this-secret" not in str(error.value)


def test_valid_provider_bearer_is_used_on_sandbox_domain_only(monkeypatch):
    monkeypatch.setenv("PAYPAL_CLIENT_ID","fake-client")
    monkeypatch.setenv("PAYPAL_CLIENT_SECRET","fake-secret")
    calls=fake_client(monkeypatch,
        oauth={"access_token":"A21A_Sandbox-Token.9"},
        response={"id":"SANDBOX-ORDER-12345"})
    result=asyncio.run(paypal.api("POST","/v2/checkout/orders",{"intent":"CAPTURE"}))
    assert result["id"]=="SANDBOX-ORDER-12345"
    assert len([item for item in calls if item[0]=="token"])==1
    api_call=next(x for x in calls if x[0]=="api")
    assert api_call[2]=="https://api-m.sandbox.paypal.com/v2/checkout/orders"
    assert api_call[3]["headers"]["Authorization"]=="Bearer A21A_Sandbox-Token.9"
    assert "fake-secret" not in str(api_call)


@pytest.mark.parametrize("payload", [
    None, [], [1], 5, "not-json-object", True,
    ValueError("broken JSON"), TypeError("bad upstream JSON")
])
def test_nonobject_provider_api_response_rejected_as_502_with_no_raw_payload(
    monkeypatch,payload
):
    async def fake_token():
        return "sandbox-test-token"
    monkeypatch.setattr(paypal,"token",fake_token)
    calls=fake_client(monkeypatch,response=payload)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(paypal.api("POST","/v2/checkout/orders",{"intent":"CAPTURE"}))
    assert exc.value.status_code==502
    assert exc.value.detail=="PayPal sandbox request failed"
    assert len([x for x in calls if x[0]=="api"])==1


@pytest.mark.parametrize("payload", [
    None, [], "malformed", 5, {"links":None}, {"links":"yes"},
    {"links":[None,0,{},{"rel":"approve","href":None}]},
    {"links":[{"rel":"approve","href":"javascript:alert(1)"}]},
    {"links":[{"rel":"approve","href":"https://paypal.com.evil.example/checkoutnow"}]},
    {"links":[{"rel":"approve","href":"https://www.sandbox.paypal.com/checkoutnow#fragment"}]},
    {"links":[{"rel":"approve","href":"https://www.sandbox.paypal.com/checkoutnow\r\nHost:evil"}]},
    {"links":[{"rel":"approve","href":"https://www.sandbox.paypal.com:444/checkoutnow"}]},
    {"links":[{"rel":"approve","href":"https://owner:secret@www.sandbox.paypal.com/checkoutnow"}]},
    {"links":[{"rel":"approve","href":"https://www.sandbox.paypal.com/checkoutnow"}]*51},
])
def test_bad_sandbox_approval_link_shapes_fail_without_uncontrolled_exception(payload):
    assert paypal.approval_link(payload) is None


def test_mixed_links_skip_bad_entries_and_accept_only_sandbox_paypal():
    good="https://www.sandbox.paypal.com/checkoutnow?token=SANDBOX-TEST"
    info={
      "links":[
        None, "not-a-link", {"rel":"approve","href":"https://evil.example/checkoutnow"},
        {"rel":"self","href":good},
        {"rel":"payer-action","href":good},
      ]
    }
    assert paypal.approval_link(info)==good
    assert paypal.trusted_sandbox_checkout_url(good)
    assert not paypal.trusted_sandbox_checkout_url(good+"\nContent-Disposition: attachment")


@pytest.mark.parametrize("target,hosted,expected", [
    ("https://circlesplit-ai-demo.onrender.com/workspace?payment=return", False, True),
    ("https://circlesplit-ai-demo.onrender.com/workspace?payment=return", True, True),
    ("http://localhost:8000/workspace?payment=return", False, True),
    ("http://127.0.0.1:8000/workspace?payment=return", False, True),
    ("http://localhost:8000/workspace?payment=return", True, False),
    ("http://demo.example/workspace?payment=return", False, False),
    ("https://demo.example/public?payment=return", False, False),
    ("https://demo.example/workspace?payment=cancelled", False, False),
    ("https://demo.example/workspace?payment=return#x", False, False),
    ("https://demo.example/workspace?payment=return\nBad: header", False, False),
    ("https://u:p@demo.example/workspace?payment=return", False, False),
    ("file://localhost/workspace?payment=return", False, False),
    ("javascript://localhost/workspace?payment=return", False, False),
    ("https://demo.example:wrong/workspace?payment=return", False, False),
    (None, False, False),
    ([], False, False),
])
def test_return_url_must_use_trusted_scheme_and_workspace_callback(
    monkeypatch,target,hosted,expected
):
    if hosted:
        monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    else:
        monkeypatch.delenv("CIRCLESPLIT_HOSTED",raising=False)
    assert paypal.trusted_checkout_return_url(target) is expected


def test_invalid_return_url_stops_before_paypal_order_network(monkeypatch):
    calls=[]
    async def fake_api(*args,**kwargs):
        calls.append(args)
        return {"id":"UNEXPECTED-ORDER",
          "links":[{"rel":"payer-action","href":
             "https://www.sandbox.paypal.com/checkoutnow?token=TEST"}]}
    monkeypatch.setattr(paypal,"api",fake_api)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(paypal.order(
            1100,1,10,"http://malicious.example/workspace?payment=return",
            "request-key"))
    assert exc.value.status_code==400
    assert "trusted HTTPS" in exc.value.detail
    assert calls==[]


@pytest.mark.parametrize("remote_result",[
    None, [], "unexpected", {"id":"INVALID ORDER","links":[]},
    {"id":"ORDER-TEST-123","links":None},
    {"id":"ORDER-TEST-123","links":[None,0]},
    {"id":"ORDER-TEST-123","links":[
        {"rel":"payer-action","href":"https://evil.example/steal"}]},
])
def test_direct_order_rejects_unsafe_provider_response(remote_result,monkeypatch):
    async def provider(*args,**kwargs):
        return remote_result
    monkeypatch.setattr(paypal,"api",provider)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(paypal.order(
            1100,1,10,
            "https://circlesplit-ai-demo.onrender.com/workspace?payment=return",
            "immutable-request-key"))
    assert exc.value.status_code==502
    assert "trusted sandbox approval link" in exc.value.detail


def test_webhook_malformed_verification_envelope_never_verifies(monkeypatch):
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID","test-signed-webhook-id")
    async def bad_api(*args,**kwargs):
        return None
    monkeypatch.setattr(paypal,"api",bad_api)
    headers={
       "paypal-auth-algo":"SHA256withRSA",
       "paypal-cert-url":"https://api-m.sandbox.paypal.com/v1/notifications/certs/CERT-360caa42-fca2a594-ab66f33d",
       "paypal-transmission-id":"test-id",
       "paypal-transmission-sig":"fake-test-signature",
       "paypal-transmission-time":"2026-11-06T16:00:00Z"
    }
    with pytest.raises(HTTPException) as exc:
        asyncio.run(paypal.verify_webhook(headers,{"id":"WH-TEST-001"}))
    assert exc.value.status_code==401


@pytest.mark.parametrize("method,identifier", [
    ("capture","../ESCAPE-ORDER"),
    ("capture","ORDER-\u00f8"),
    ("capture","A"*51),
    ("details","../ESCAPE-ORDER"),
    ("details",None),
    ("details",123)
])
def test_provider_adapter_rejects_order_id_before_network(
    monkeypatch,method,identifier
):
    calls=[]
    async def no_request(*args,**kwargs):
        calls.append(args)
        raise AssertionError("No provider request is allowed for an unsafe order ID")
    monkeypatch.setattr(paypal,"api",no_request)
    with pytest.raises(HTTPException) as exc:
        if method=="capture":
            asyncio.run(paypal.capture(identifier,"capture-key"))
        else:
            asyncio.run(paypal.details(identifier))
    assert exc.value.status_code==400
    assert calls==[]


@pytest.fixture
def hosted(monkeypatch,tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"sandbox-callback.sqlite3"))
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_USERNAME",OWNER[0])
    monkeypatch.setenv("DEMO_PASSWORD",OWNER[1])
    monkeypatch.delenv("PUBLIC_BASE_URL",raising=False)
    monkeypatch.delenv("RENDER_EXTERNAL_URL",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def chosen(hosted):
    event=hosted.get("/api/state",auth=OWNER).json()["events"][0]
    return event["id"],event["people"][0]["id"]


def payment_attempt_count():
    import app
    with app.db() as c:
        return c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]


def test_hosted_missing_callback_blocks_preflight_before_payment_row(
    hosted,monkeypatch
):
    eid,pid=chosen(hosted)
    monkeypatch.setattr(paypal,"configured",lambda:True)
    assert hosted.post(f"/api/events/{eid}/people/{pid}/approve",
                       auth=OWNER).status_code==200
    remote=[]
    async def forbidden(*args,**kwargs):
        remote.append(args)
        raise AssertionError("No PayPal call is allowed")
    monkeypatch.setattr(paypal,"order",forbidden)
    ready=hosted.get(f"/api/paypal/checkout-readiness/{eid}/{pid}",
                     auth=OWNER)
    assert ready.status_code==200
    assert ready.json()["can_create_order"] is False
    assert "sandbox_return_url_unconfigured" in {
        item["code"] for item in ready.json()["blockers"]
    }
    assert payment_attempt_count()==0
    result=hosted.post(f"/api/paypal/orders/{eid}/{pid}",auth=OWNER)
    assert result.status_code==503
    assert "No payment attempt" in result.json()["detail"]
    assert remote==[]
    assert payment_attempt_count()==0
    import app
    with app.db() as c:
        assert c.execute(
            "SELECT COUNT(*) FROM event_history WHERE action='sandbox_order_started'"
        ).fetchone()[0]==0


def test_hosted_invalid_callback_does_not_lock_any_person_or_make_order(
    hosted,monkeypatch
):
    eid,pid=chosen(hosted)
    assert hosted.post(f"/api/events/{eid}/people/{pid}/approve",
                       auth=OWNER).status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    monkeypatch.setenv("PUBLIC_BASE_URL","http://malicious.example")
    response=hosted.post(f"/api/paypal/orders/{eid}/{pid}",auth=OWNER)
    assert response.status_code==503
    assert payment_attempt_count()==0
    monkeypatch.setenv("PUBLIC_BASE_URL","https://example.com/evil-path")
    ready=hosted.get(f"/api/paypal/checkout-readiness/{eid}/{pid}",auth=OWNER)
    assert "sandbox_return_url_unconfigured" in {
        item["code"] for item in ready.json()["blockers"]
    }
    assert payment_attempt_count()==0


def test_hosted_valid_public_origin_ignores_request_host_and_creates_one_order(
    hosted,monkeypatch
):
    eid,pid=chosen(hosted)
    assert hosted.post(f"/api/events/{eid}/people/{pid}/approve",
                       auth=OWNER).status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    monkeypatch.setenv("PUBLIC_BASE_URL",
                       "https://circlesplit-ai-demo.onrender.com")
    seen=[]
    async def mocked_order(amount,eid,pid,return_url,request_id):
        seen.append((amount,eid,pid,return_url))
        return {"id":"SAFE-CALLBACK-ORDER-123",
                "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"}
    monkeypatch.setattr(paypal,"order",mocked_order)
    ready=hosted.get(f"/api/paypal/checkout-readiness/{eid}/{pid}",
                     auth=OWNER)
    assert ready.status_code==200
    assert ready.json()["can_create_order"] is True
    result=hosted.post(f"/api/paypal/orders/{eid}/{pid}",
        auth=OWNER,headers={"host":"attacker-host.example"})
    assert result.status_code==200,result.text
    assert seen[0][3]=="https://circlesplit-ai-demo.onrender.com/workspace?payment=return"
    assert payment_attempt_count()==1


def test_render_external_url_fallback_is_trusted_only_if_https(
    hosted,monkeypatch
):
    import app
    from starlette.requests import Request
    monkeypatch.setenv("RENDER_EXTERNAL_URL",
                       "https://circlesplit-ai-demo.onrender.com")
    request=Request({"type":"http","method":"GET","path":"/",
                     "headers":[],"scheme":"https","server":("wrong.example",443)})
    assert app.sandbox_checkout_return_url(request)==(
       "https://circlesplit-ai-demo.onrender.com/workspace?payment=return")
    monkeypatch.setenv("RENDER_EXTERNAL_URL","http://wrong.example")
    assert app.sandbox_checkout_return_url(request) is None
