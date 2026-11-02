"""Offline tests. Mock PayPal; these do not prove a real sandbox transaction."""
import importlib
import pytest
from fastapi.testclient import TestClient
from domain import cents, allocate
import paypal

def test_strict_cents():
    assert cents("1.23")==123
    for bad in ["0","-1","nan","1.999","100000.01","infinity",None]:
        with pytest.raises(ValueError): cents(bad)

def test_equal_and_weighted_exact():
    people=[{"id":5,"weight":1},{"id":2,"weight":1},{"id":9,"weight":1}]
    assert allocate(100,people)=={2:34,5:33,9:33}
    assert sum(allocate(22000,people).values())==22000
    people=[{"id":6,"weight":3},{"id":1,"weight":1},{"id":3,"weight":2}]
    assert allocate(100,people,"weighted")=={1:17,3:33,6:50}
    assert allocate(100,people,"weighted")==allocate(100,list(reversed(people)),"weighted")

def test_paypal_amount_validation():
    assert paypal.same_amount("19.04",1904)
    assert not paypal.same_amount("19.05",1904)
    assert not paypal.same_amount("NaN",1904)
    assert paypal.completed_capture(
        {"purchase_units":[{"payments":{"captures":[
            {"id":"C1","status":"COMPLETED","amount":{"currency_code":"USD","value":"3.01"}}
        ]}}]},301)["id"]=="C1"
    assert paypal.completed_capture({"purchase_units":[]},301) is None

@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"test.sqlite3"))
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    monkeypatch.delenv("GEMINI_API_KEY",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance

def initial(client):
    return client.get("/api/state").json()["events"][0]

def test_health_and_seed(client):
    assert client.get("/").status_code==200
    assert client.get("/health").json()["mode"]=="sandbox-only"
    e=initial(client)
    assert e["total_cents"]==22000 and len(e["people"])==20
    assert sum(p["share_cents"] for p in e["people"])==22000

def test_approval_simulation_and_lock(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    path=f"/api/events/{eid}/people/{pid}"
    assert client.post(path+"/simulate").status_code==409
    assert client.post(path+"/approve").status_code==200
    assert client.post(path+"/simulate").json()["mode"]=="SIMULATED - NOT PAYPAL"
    assert client.post(path+"/simulate").status_code==409
    updated=initial(client)
    assert updated["simulated_cents"]==e["people"][0]["share_cents"]
    assert updated["sandbox_cents"]==0
    assert client.post(f"/api/events/{eid}/allocation",json={"strategy":"weighted"}).status_code==409

def test_cost_edit_clears_approvals(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    assert client.post(f"/api/events/{eid}/expenses",json={"title":"Extra cost","amount":"0.01"}).status_code==200
    updated=initial(client)
    assert updated["approved"]==0
    assert sum(x["share_cents"] for x in updated["people"])==22001

def test_create_event_and_validation(client):
    e=client.post("/api/events",json={"name":"Game night","date":"2026-11-04","note":"6 friends"}).json()
    eid=e["id"]
    assert client.post(f"/api/events/{eid}/expenses",json={"title":"Room","amount":"50.00"}).status_code==200
    assert client.post(f"/api/events/{eid}/expenses",json={"title":"Bad","amount":"1.999"}).status_code==422
    for name in ["Ava","Max","Lee"]:
        assert client.post(f"/api/events/{eid}/people",json={"name":name}).status_code==200
    row=next(x for x in client.get("/api/state").json()["events"] if x["id"]==eid)
    assert sum(p["share_cents"] for p in row["people"])==5000

def test_provider_gates(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    assert client.post("/api/ai/parse",json={"note":"Court 100 dollars and equipment 25 dollars"}).status_code==503
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==503

def test_mocked_order_uses_server_amount(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    recorded=[]
    async def fake_order(amount,eid_arg,pid_arg,url,key):
        recorded.append((amount,eid_arg,pid_arg,key))
        return {"id":"TEST-ORDER-123","approval_url":"https://www.sandbox.paypal.com/test"}
    monkeypatch.setattr(paypal,"configured",lambda:True)
    monkeypatch.setattr(paypal,"order",fake_order)
    response=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert response.status_code==200
    assert recorded[0][0]==e["people"][0]["share_cents"]
    assert recorded[0][1:3]==(eid,pid)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==409

def test_mocked_capture_and_webhook_replay(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    client.post(f"/api/events/{eid}/people/{pid}/approve")
    monkeypatch.setattr(paypal,"configured",lambda:True)
    async def fake_order(*args):
        return {"id":"TEST-ORDER-456","approval_url":"https://www.sandbox.paypal.com/test"}
    async def fake_capture(*args):
        return {"purchase_units":[{"payments":{"captures":[{
          "id":"CAPTURE-1","status":"COMPLETED",
          "amount":{"currency_code":"USD","value":f"{e['people'][0]['share_cents']/100:.2f}"}
        }]}}]}
    monkeypatch.setattr(paypal,"order",fake_order)
    monkeypatch.setattr(paypal,"capture",fake_capture)
    client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert client.post("/api/paypal/capture",json={"order_id":"TEST-ORDER-456"}).status_code==200
    assert client.post("/api/paypal/capture",json={"order_id":"TEST-ORDER-456"}).json()["already_recorded"] is True
    assert initial(client)["sandbox_cents"]==e["people"][0]["share_cents"]
    assert initial(client)["simulated_cents"]==0
    async def verified(*args): return True
    monkeypatch.setattr(paypal,"verify_webhook",verified)
    event={"id":"WH1","event_type":"PAYMENT.CAPTURE.COMPLETED",
           "resource":{"id":"CAPTURE-1","status":"COMPLETED",
               "amount":{"currency_code":"USD","value":f"{e['people'][0]['share_cents']/100:.2f}"},
               "supplementary_data":{"related_ids":{"order_id":"TEST-ORDER-456"}}}}
    assert client.post("/api/paypal/webhook",json=event).status_code==200
    assert client.post("/api/paypal/webhook",json=event).json()["duplicate"] is True


def test_hosted_demo_fails_closed_and_accepts_explicit_credentials(client,monkeypatch):
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.delenv("DEMO_PASSWORD",raising=False)
    assert client.get("/api/state").status_code == 503
    monkeypatch.setenv("DEMO_PASSWORD","a-long-random-demo-password")
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/state",auth=("wrong","a-long-random-demo-password")).status_code == 401
    assert client.get("/api/state",auth=("judge","a-long-random-demo-password")).status_code == 200
    assert client.get("/health").status_code == 200


def test_mocked_ai_proposal_is_review_only(client, monkeypatch):
    """Mocked provider output must never mutate an event without explicit approval."""
    import app as api_module
    monkeypatch.setenv("GEMINI_API_KEY","test-fake-key")
    original = initial(client)["total_cents"]
    class FakeResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"candidates":[{"content":{"parts":[{"text":
                '{"expenses":[{"title":"Court","amount":"19.95"}],"strategy":"weighted","rationale":"Usage differs"}'
            }]}}]}
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,*args,**kwargs): return FakeResponse()
    monkeypatch.setattr(api_module.httpx,"AsyncClient",FakeAsyncClient)
    response=client.post("/api/ai/parse",json={"note":"The court price is nineteen dollars and ninety five cents"})
    assert response.status_code==200
    body=response.json()
    assert body["requires_approval"] is True
    assert body["expenses"]==[{"title":"Court","amount":"19.95"}]
    assert body["strategy"]=="weighted"
    assert initial(client)["total_cents"]==original


def test_deletion_reallocates_and_payment_locks(client):
    e=initial(client);eid=e["id"]
    expense_id=e["expenses"][0]["id"]
    p=e["people"][0]["id"]
    assert client.delete(f"/api/events/{eid}/expenses/{expense_id}").status_code==200
    current=initial(client)
    assert current["total_cents"]==6000
    assert sum(x["share_cents"] for x in current["people"])==6000
    assert client.delete(f"/api/events/{eid}/people/{p}").status_code==200
    current=initial(client)
    assert len(current["people"])==19
    assert sum(x["share_cents"] for x in current["people"])==6000
    pid=current["people"][0]["id"]
    client.post(f"/api/events/{eid}/people/{pid}/approve")
    client.post(f"/api/events/{eid}/people/{pid}/simulate")
    assert client.delete(f"/api/events/{eid}/expenses/{current['expenses'][0]['id']}").status_code==409
    assert client.delete(f"/api/events/{eid}/people/{current['people'][1]['id']}").status_code==409


def test_public_demo_is_open_but_organizer_actions_stay_protected(client, monkeypatch):
    """Public visitors can interact with a browser-local demo, not the shared backend."""
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.setenv("DEMO_USERNAME", "judge")
    monkeypatch.setenv("DEMO_PASSWORD", "long-and-unguessable-demo-pass")
    page = client.get("/")
    assert page.status_code == 200
    assert "Public interactive demo" in page.text
    assert "No PayPal orders or AI API requests" in page.text
    assert "localStorage" in page.text
    assert client.get("/favicon.ico").status_code == 204
    assert client.head("/favicon.ico").status_code == 204
    assert client.get("/workspace").status_code == 401
    assert client.get("/api/state").status_code == 401
    assert client.get("/api/transactions").status_code == 401
    assert client.post("/api/events", json={"name":"Spam","date":"2026-11-06"}).status_code == 401
    assert client.post("/api/ai/parse", json={"note":"some long enough input"}).status_code == 401
    assert client.post("/api/paypal/orders/1/10").status_code == 401
    assert client.get("/static/index.html").status_code == 401
    assert client.get("/workspace",auth=("judge","long-and-unguessable-demo-pass")).status_code == 200
    assert client.get("/api/state",auth=("judge","long-and-unguessable-demo-pass")).status_code == 200


def test_paypal_approval_returns_to_protected_workspace(client, monkeypatch):
    """After public root release, a sandbox checkout must return to organizer UI."""
    e = initial(client)
    eid, pid = e["id"], e["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 200
    monkeypatch.setattr(paypal, "configured", lambda: True)
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://circlesplit-ai-demo.onrender.com")
    captured = []
    async def fake_order(amount, event_id, person_id, url, request_id):
        captured.append(url)
        return {"id":"TEST-ORDER-RETURN-42","approval_url":"https://www.sandbox.paypal.com/test"}
    monkeypatch.setattr(paypal,"order",fake_order)
    r = client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert r.status_code == 200
    assert captured == ["https://circlesplit-ai-demo.onrender.com/workspace?payment=return"]


@pytest.mark.parametrize("provider_status,expected", [
    (400, "Gemini HTTP 400: Invalid request"),
    (403, "Gemini HTTP 403: API key"),
    (404, "Gemini HTTP 404: Model not available"),
    (429, "Gemini HTTP 429: Quota"),
    (503, "Gemini HTTP 503: Google service"),
])
def test_gemini_error_codes_are_actionable_without_leaking_provider_details(
    client, monkeypatch, provider_status, expected
):
    import app as api_module
    import httpx
    monkeypatch.setenv("GEMINI_API_KEY", "non-secret-fixture-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    outbound = []
    class BadResponse:
        def raise_for_status(self):
            request = httpx.Request("POST", "https://generativelanguage.googleapis.com/v1beta/models/test:generateContent")
            response = httpx.Response(
                provider_status,
                request=request,
                json={"error": {"message": "DO NOT LEAK PRIVATE PROVIDER DIAGNOSTICS"}},
            )
            raise httpx.HTTPStatusError("Provider failure", request=request, response=response)
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            outbound.append(url)
            return BadResponse()
    monkeypatch.setattr(api_module.httpx, "AsyncClient", FakeClient)
    response = client.post("/api/ai/parse", json={"note":"Rental 160 USD, snacks 30 USD"})
    assert response.status_code == 502
    assert expected in response.json()["detail"]
    assert "PRIVATE PROVIDER" not in response.text
    assert outbound and "/models/gemini-3.5-flash-lite:generateContent" in outbound[0]


def test_gemini_invalid_json_is_reported_distinctly(client, monkeypatch):
    import app as api_module
    monkeypatch.setenv("GEMINI_API_KEY", "non-secret-fixture-key")
    class BadResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"candidates":[{"content":{"parts":[{"text":"not-json"}]}}]}
    class FakeClient:
        def __init__(self, *args, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, *args, **kwargs): return BadResponse()
    monkeypatch.setattr(api_module.httpx, "AsyncClient", FakeClient)
    response = client.post("/api/ai/parse", json={"note":"Rental 160 USD, snacks 30 USD"})
    assert response.status_code == 502
    assert "invalid or incomplete structured JSON" in response.json()["detail"]


@pytest.mark.parametrize("status,expected_action", [
    ("PAYER_ACTION_REQUIRED", "approve"),
    ("CREATED", "approve"),
    ("APPROVED", "capture"),
    ("COMPLETED", "done"),
])
def test_existing_sandbox_order_recovery(client, monkeypatch, status, expected_action):
    """Never reissue a created order; reconcile only matching PayPal amounts."""
    e = initial(client)
    eid, pid = e["id"], e["people"][0]["id"]
    amount = e["people"][0]["share_cents"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code == 200
    monkeypatch.setattr(paypal, "configured", lambda: True)
    order_id = "TEST-ORDER-STATUS-42"
    async def fake_order(*args):
        return {"id":order_id,"approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"}
    monkeypatch.setattr(paypal, "order", fake_order)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code == 200
    detail = {
        "id":order_id,"intent":"CAPTURE","status":status,
        "purchase_units":[{
            "custom_id":f"{eid}:{pid}",
            "amount":{"currency_code":"USD","value":f"{amount/100:.2f}"},
            "payments":{"captures":[{"id":"TEST-CAPTURE-42", "status":"COMPLETED",
                "amount":{"currency_code":"USD","value":f"{amount/100:.2f}"}}]} if status=="COMPLETED" else {},
        }],
        "links":[{"rel":"payer-action","href":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"}],
    }
    async def fake_details(*args):
        return detail
    monkeypatch.setattr(paypal, "details",fake_details)
    result=client.post(f"/api/paypal/order-status/{order_id}")
    assert result.status_code == 200, result.text
    body=result.json()
    assert body["action"] == expected_action
    assert body["verified"] == (status=="COMPLETED")
    if status in ("PAYER_ACTION_REQUIRED","CREATED"):
        assert body["approval_url"].startswith("https://www.sandbox.paypal.com/")
    if status == "COMPLETED":
        assert initial(client)["sandbox_cents"] == amount
        assert client.post(f"/api/paypal/order-status/{order_id}").json()["action"] == "done"
    else:
        assert initial(client)["sandbox_cents"] == 0
    # Repeated order creation is blocked, regardless of PayPal's current state.
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code == 409


def test_sandbox_recovery_rejects_amount_mismatch_and_forged_link(client, monkeypatch):
    e=initial(client);eid,pid=e["id"],e["people"][0]["id"]
    client.post(f"/api/events/{eid}/people/{pid}/approve")
    monkeypatch.setattr(paypal,"configured",lambda:True)
    order_id = "TEST-ORDER-VALIDATION-42"
    async def fake_order(*args):
        return {"id":order_id,"approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=T"}
    monkeypatch.setattr(paypal,"order",fake_order)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==200
    data={"id":order_id,"intent":"CAPTURE","status":"PAYER_ACTION_REQUIRED",
          "purchase_units":[{"custom_id":f"{eid}:{pid}",
                             "amount":{"currency_code":"USD","value":"999.00"}}],
          "links":[{"rel":"payer-action","href":"https://evil.example/checkoutnow"}]}
    async def fake_details(*args): return data
    monkeypatch.setattr(paypal,"details",fake_details)
    assert client.post(f"/api/paypal/order-status/{order_id}").status_code==409
    assert initial(client)["sandbox_cents"]==0
    data["purchase_units"][0]["amount"]["value"]=f'{e["people"][0]["share_cents"]/100:.2f}'
    result=client.post(f"/api/paypal/order-status/{order_id}")
    assert result.status_code==200
    assert result.json()["action"]=="pending"
    assert result.json()["approval_url"] is None
    assert paypal.approval_link({"links":[{"rel":"payer-action","href":"https://paypal.com.evil.example/steal"}]}) is None


def test_unknown_sandbox_order_cannot_be_queried(client,monkeypatch):
    async def no_remote_call(*args): raise AssertionError("Remote lookup must not occur")
    monkeypatch.setattr(paypal,"details",no_remote_call)
    assert client.post("/api/paypal/order-status/UNKNOWN-ORDER").status_code==404
