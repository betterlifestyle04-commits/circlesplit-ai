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
    assert body["expenses"]==[{"title":"Court","amount":"19.95","category":"other"}]
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

def test_judge_login_expiration_and_public_guide(client,monkeypatch):
    monkeypatch.setenv("CIRCLESPLIT_HOSTED", "1")
    monkeypatch.setenv("DEMO_USERNAME", "owner")
    monkeypatch.setenv("DEMO_PASSWORD", "long-owner-password-for-tests")
    monkeypatch.setenv("JUDGE_ACCESS_ENABLED", "1")
    monkeypatch.setenv("JUDGE_USERNAME", "reviewer")
    monkeypatch.setenv("JUDGE_PASSWORD", "long-independent-judge-password-for-tests")
    monkeypatch.setenv("JUDGE_ACCESS_EXPIRES_AT", "2026-12-16T23:59:00+00:00")
    assert client.get("/judge").status_code == 200
    assert "Judge walkthrough" in client.get("/judge").text
    assert client.get("/api/judge-readiness").status_code == 401
    assert client.get("/api/state",auth=("reviewer","long-independent-judge-password-for-tests")).status_code == 200
    assert client.get("/workspace",auth=("reviewer","long-independent-judge-password-for-tests")).status_code == 200
    assert client.get("/api/state",auth=("owner","long-owner-password-for-tests")).status_code == 200
    assert client.get("/api/state",auth=("reviewer","wrong-password")).status_code == 401
    status = client.get("/api/judge-readiness",auth=("reviewer","long-independent-judge-password-for-tests"))
    assert status.status_code == 200
    assert status.json()["storage"] == "ephemeral-sqlite"
    assert status.json()["current_store_verified_captures"] == 0
    assert "JUDGE_PASSWORD" not in status.text
    monkeypatch.setenv("JUDGE_ACCESS_EXPIRES_AT", "2025-12-16T00:00:00+00:00")
    assert client.get("/api/state",auth=("reviewer","long-independent-judge-password-for-tests")).status_code == 401
    assert client.get("/api/state",auth=("owner","long-owner-password-for-tests")).status_code == 200
    monkeypatch.setenv("JUDGE_ACCESS_EXPIRES_AT","broken")
    assert client.get("/api/state",auth=("reviewer","long-independent-judge-password-for-tests")).status_code == 401
    monkeypatch.setenv("JUDGE_ACCESS_ENABLED","0")
    assert client.get("/api/state",auth=("reviewer","long-independent-judge-password-for-tests")).status_code == 401


def test_public_guide_and_homepage_need_no_secret(client,monkeypatch):
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","random-owner-password-for-tests")
    assert client.get("/").status_code == 200
    assert client.get("/judge").status_code == 200
    assert client.get("/workspace").status_code == 401
    assert client.post("/api/ai/parse",json={"note":"Court 180 dollars, equipment 25 dollars"}).status_code == 401


def test_clone_event_copies_budget_but_not_payments(client,monkeypatch):
    """Event templates must never duplicate approvals, simulated or real money."""
    e=initial(client);eid=e["id"];first=e["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{first}/approve").status_code==200
    assert client.post(f"/api/events/{eid}/people/{first}/simulate").status_code==200
    result=client.post(f"/api/events/{eid}/clone",json={
        "name":"Second Friday Volleyball","date":"2026-11-13","include_people":True
    })
    assert result.status_code==200,result.text
    info=result.json()
    assert info["copied_expenses"]==3
    assert info["copied_people"]==20
    assert info["payments_copied"] is False
    cloned=next(x for x in client.get("/api/state").json()["events"] if x["id"]==info["id"])
    assert cloned["name"]=="Second Friday Volleyball"
    assert cloned["total_cents"]==22000
    assert sum(x["share_cents"] for x in cloned["people"])==22000
    assert all(x["approved"]==0 and x["status"]=="unpaid" for x in cloned["people"])
    assert cloned["sandbox_cents"]==0 and cloned["simulated_cents"]==0
    original=next(x for x in client.get("/api/state").json()["events"] if x["id"]==eid)
    assert original["simulated_cents"]==1100


def test_clone_without_people_and_original_payment_lock(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    client.post(f"/api/events/{eid}/people/{pid}/approve")
    client.post(f"/api/events/{eid}/people/{pid}/simulate")
    r=client.post(f"/api/events/{eid}/clone",json={"include_people":False})
    assert r.status_code==200
    cloned=next(x for x in client.get("/api/state").json()["events"] if x["id"]==r.json()["id"])
    assert cloned["people"]==[]
    assert cloned["total_cents"]==e["total_cents"]
    assert r.json()["copied_people"]==0
    assert client.post(f"/api/events/{eid}/allocation",json={"strategy":"weighted"}).status_code==409
    assert client.post(f"/api/events/{cloned['id']}/people",json={"name":"New person"}).status_code==200


def test_scenario_preview_is_exact_and_read_only(client):
    e=initial(client);eid=e["id"]
    current=client.get("/api/state").json()
    r=client.post(f"/api/events/{eid}/scenario",json={
        "adjustment":"10.00","additional_people":1,"strategy":"equal"
    })
    assert r.status_code==200,r.text
    d=r.json()
    assert d["read_only"] is True
    assert d["scenario_total_cents"]==23000
    assert d["current_people"]==20 and d["scenario_people"]==21
    assert sum(x["after_cents"] for x in d["shares"])==23000
    assert sum(x["before_cents"] for x in d["shares"])==22000
    assert sum(x["change_cents"] for x in d["shares"])==1000
    assert d["added_people"]==1
    assert client.get("/api/state").json()==current
    assert client.get("/api/transactions").json()["transactions"]==[]


def test_scenario_weighted_discount_and_lock_are_read_only(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    client.post(f"/api/events/{eid}/people/{pid}/approve")
    client.post(f"/api/events/{eid}/people/{pid}/simulate")
    before=client.get("/api/state").json()
    r=client.post(f"/api/events/{eid}/scenario",json={
        "adjustment":"-20.00","additional_people":2,"strategy":"weighted"
    })
    assert r.status_code==200,r.text
    d=r.json()
    assert d["scenario_total_cents"]==20000
    assert d["strategy"]=="weighted"
    assert sum(p["after_cents"] for p in d["shares"])==20000
    assert d["read_only"] is True
    assert client.get("/api/state").json()==before


@pytest.mark.parametrize("payload",[
    {"adjustment":"-300.00"},
    {"adjustment":"NaN"},
    {"adjustment":"0.001"},
    {"adjustment":"1000000.00"},
    {"additional_people":51},
    {"additional_people":-1},
    {"strategy":"random"},
])
def test_scenario_rejects_bad_input(client,payload):
    eid=initial(client)["id"]
    assert client.post(f"/api/events/{eid}/scenario",json=payload).status_code==422


def test_scenario_requires_participants(client):
    created=client.post("/api/events",json={"name":"Empty Event","date":"2026-11-13"}).json()
    assert client.post(f"/api/events/{created['id']}/scenario",json={}).status_code==422
    r=client.post(f"/api/events/{created['id']}/scenario",json={"additional_people":3})
    assert r.status_code==200
    assert sum(x["after_cents"] for x in r.json()["shares"])==0


def test_scenario_and_clone_routes_are_protected(client,monkeypatch):
    eid=initial(client)["id"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","very-long-owner-password")
    assert client.post(f"/api/events/{eid}/scenario",json={}).status_code==401
    assert client.post(f"/api/events/{eid}/clone",json={}).status_code==401


def test_bulk_people_import_is_atomic_and_accurate(client):
    e=client.post("/api/events",json={"name":"New Team","date":"2026-11-15"}).json()
    eid=e["id"]
    client.post(f"/api/events/{eid}/expenses",json={"title":"Court","amount":"10.00"})
    result=client.post(f"/api/events/{eid}/people/bulk",json={
        "people":[{"name":"Mina","weight":2},{"name":"Rafa","weight":1},{"name":"Iman","weight":1}]
    })
    assert result.status_code==200,result.text
    assert result.json()["added"]==3
    event=next(e for e in client.get("/api/state").json()["events"] if e["id"]==eid)
    assert len(event["people"])==3
    assert sum(p["share_cents"] for p in event["people"])==1000
    assert all(not p["approved"] for p in event["people"])
    assert client.post(f"/api/events/{eid}/allocation",json={"strategy":"weighted"}).status_code==200
    event=next(e for e in client.get("/api/state").json()["events"] if e["id"]==eid)
    assert sorted(p["share_cents"] for p in event["people"])==[250,250,500]


def test_bulk_people_import_rejects_duplicates_and_does_not_partially_insert(client):
    e=initial(client);eid=e["id"]
    before=client.get("/api/state").json()
    r=client.post(f"/api/events/{eid}/people/bulk",json={
        "people":[{"name":"Unique","weight":1},{"name":"unique","weight":2}]
    })
    assert r.status_code==422
    r=client.post(f"/api/events/{eid}/people/bulk",json={
        "people":[{"name":"Unique","weight":1},{"name":"Alex","weight":1}]
    })
    assert r.status_code==409
    assert client.get("/api/state").json()==before
    r=client.post(f"/api/events/{eid}/people/bulk",json={
        "people":[{"name":"Unique","weight":11},{"name":"Other","weight":1}]
    })
    assert r.status_code==422
    assert client.get("/api/state").json()==before


def test_bulk_people_import_respects_payment_locks(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    client.post(f"/api/events/{eid}/people/{pid}/approve")
    client.post(f"/api/events/{eid}/people/{pid}/simulate")
    assert client.post(f"/api/events/{eid}/people/bulk",json={
        "people":[{"name":"NewOne","weight":1}]
    }).status_code==409


def test_participant_invitation_is_private_and_approves_only_own_share(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","long-demo-owner-password")
    owner=("judge","long-demo-owner-password")
    assert client.get("/participant").status_code==200
    assert client.get("/api/participant/overview").status_code==401
    assert client.post(f"/api/events/{eid}/people/{pid}/invite").status_code==401
    out=client.post(f"/api/events/{eid}/people/{pid}/invite",auth=owner)
    assert out.status_code==200,out.text
    token=out.json()["token"]
    assert len(token)>=40
    assert "https://" not in out.text and "PRIVATE" not in out.text
    headers={"Authorization":"Bearer "+token}
    detail=client.get("/api/participant/overview",headers=headers)
    assert detail.status_code==200
    d=detail.json()
    assert set(d)=={"event_name","event_date","participant","share_cents","approved",
                    "approval_source","status","rsvp_status","expires_at","currency","payment_mode","identity_verified"}
    assert d["participant"]=="Alex" and d["share_cents"]==1100
    assert d["rsvp_status"]=="pending"
    assert d["identity_verified"] is False and d["payment_mode"]=="NONE"
    assert detail.headers.get("Cache-Control")=="no-store"
    assert "no-referrer"==detail.headers.get("Referrer-Policy")
    assert client.post("/api/participant/approve",headers=headers).json()["approval_source"]=="participant_link"
    again=client.post("/api/participant/approve",headers=headers)
    assert again.status_code==200 and again.json()["already_approved"] is True
    original=next(x for x in client.get("/api/state",auth=owner).json()["events"] if x["id"]==eid)
    assert original["people"][0]["approved"]==1
    assert original["people"][0]["approval_source"]=="participant_link"
    assert all(not x["approved"] for x in original["people"][1:])
    assert client.post(f"/api/paypal/orders/{eid}/{pid}",headers=headers).status_code==401
    assert client.get("/api/state",headers=headers).status_code==401
    assert client.get("/api/transactions",headers=headers).status_code==401
    assert client.post("/api/ai/parse",json={"note":"court fee $180 and snacks $35"},headers=headers).status_code==401


def test_revocation_rotation_and_expiry(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    import app as api
    t1=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    t2=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    assert t1!=t2
    assert client.get("/api/participant/overview",headers={"Authorization":"Bearer "+t1}).status_code==404
    h2={"Authorization":"Bearer "+t2}
    assert client.get("/api/participant/overview",headers=h2).status_code==200
    with api.db() as c:
        c.execute("UPDATE participant_invites SET expires_at='2000-01-01T00:00:00+00:00'")
    assert client.get("/api/participant/overview",headers=h2).status_code==410
    t3=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    h3={"Authorization":"Bearer "+t3}
    assert client.get("/api/participant/overview",headers=h3).status_code==200
    revoked=client.post(f"/api/events/{eid}/people/{pid}/invite/revoke")
    assert revoked.status_code==200 and revoked.json()["revoked"]==1
    assert client.post("/api/participant/approve",headers=h3).status_code==404


def test_budget_change_invalidates_invite(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    h={"Authorization":"Bearer "+token}
    assert client.get("/api/participant/overview",headers=h).status_code==200
    assert client.post(f"/api/events/{eid}/expenses",json={"title":"New expense","amount":"5.00"}).status_code==200
    assert client.post("/api/participant/approve",headers=h).status_code==404


def test_invites_do_not_bypass_payment_locks(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    headers={"Authorization":"Bearer "+token}
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code==200
    assert client.post(f"/api/events/{eid}/people/{pid}/invite").status_code==409
    assert client.post("/api/participant/approve",headers=headers).status_code==409


def test_public_participant_methods_are_minimal(client,monkeypatch):
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","long-demo-owner-password")
    assert client.post("/api/participant/overview").status_code==401
    assert client.get("/api/participant/approve").status_code==401
    assert client.get("/participant").status_code==200
    assert "frame-ancestors 'none'" in client.get("/participant").headers["content-security-policy"]
    assert client.post("/api/events/1/people/10/invite/revoke").status_code==401

def test_tasks_crud_independent_of_payment_lock(client):
    event=initial(client);eid=event["id"]
    new=client.post(f"/api/events/{eid}/tasks",json={"title":"Confirm venue"})
    assert new.status_code==200,new.text
    tid=new.json()["id"]
    assert client.post(f"/api/events/{eid}/tasks",json={"title":"confirm VENUE"}).status_code==409
    assert client.patch(f"/api/events/{eid}/tasks/{tid}",json={"completed":True}).status_code==200
    assert initial(client)["tasks"][0]["completed"]==1
    pid=event["people"][0]["id"]
    client.post(f"/api/events/{eid}/people/{pid}/approve")
    client.post(f"/api/events/{eid}/people/{pid}/simulate")
    assert client.patch(f"/api/events/{eid}/tasks/{tid}",json={"completed":False}).status_code==200
    assert client.delete(f"/api/events/{eid}/tasks/{tid}").status_code==200
    assert initial(client)["simulated_cents"]==1100
    assert client.patch(f"/api/events/{eid}/tasks/{tid}",json={"completed":True}).status_code==404

def test_starter_tasks_idempotent_and_cloning_resets_them(client):
    eid=initial(client)["id"]
    assert client.post(f"/api/events/{eid}/tasks/starter").json()["added"]==5
    assert client.post(f"/api/events/{eid}/tasks/starter").json()["added"]==0
    tid=initial(client)["tasks"][0]["id"]
    client.patch(f"/api/events/{eid}/tasks/{tid}",json={"completed":True})
    copy=client.post(f"/api/events/{eid}/clone",json={"name":"Next Volleyball"})
    assert copy.status_code==200,copy.text
    assert copy.json()["copied_tasks"]==5
    target=next(x for x in client.get("/api/state").json()["events"] if x["id"]==copy.json()["id"])
    assert len(target["tasks"])==5
    assert all(x["completed"]==0 for x in target["tasks"])

def test_task_scoping_and_hosted_access(client,monkeypatch):
    eid=initial(client)["id"]
    other=client.post("/api/events",json={"name":"Other activity","date":"2026-11-07"}).json()["id"]
    tid=client.post(f"/api/events/{eid}/tasks",json={"title":"Prepare equipment"}).json()["id"]
    assert client.delete(f"/api/events/{other}/tasks/{tid}").status_code==404
    assert client.patch(f"/api/events/{other}/tasks/{tid}",json={"completed":True}).status_code==404
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","a-long-owner-demo-password")
    assert client.post(f"/api/events/{eid}/tasks",json={"title":"Forbidden"}).status_code==401
    assert client.patch(f"/api/events/{eid}/tasks/{tid}",json={"completed":True}).status_code==401
    assert client.delete(f"/api/events/{eid}/tasks/{tid}").status_code==401


def test_public_head_probe_does_not_trigger_auth(client,monkeypatch):
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","long-owner-demo-test-password")
    assert client.head("/").status_code==200
    assert client.head("/health").status_code==200
    assert client.get("/health").json()["status"]=="ok"
    assert client.head("/workspace").status_code==401


def test_ai_preparation_plan_requires_review(client,monkeypatch):
    """Mocked Gemini suggests tasks but cannot mutate stored event data."""
    import app as api
    import json
    event = initial(client)
    eid = event["id"]
    assert client.post(f"/api/events/{eid}/tasks/starter").status_code == 200
    before = client.get("/api/state").json()
    monkeypatch.setenv("GEMINI_API_KEY","fictional-test-key-not-a-real-secret")
    prompts = []
    class GoodResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"candidates":[{"content":{"parts":[{"text":json.dumps({
                "tasks":[
                    {"title":"Confirm venue"}, # already exists, filtered
                    {"title":"  Arrange   volleyball  nets "},
                    {"title":"Arrange volleyball nets"}, # duplicate, filtered
                    {"title":"Check court lighting"},
                    {"title":"Share arrival instructions"},
                    {"title":"x"},
                    {"title":"x"*145},
                ],
                "rationale":"Coordinate equipment and arrival."
            })}]}}]}
    class FakeClient:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,url,**kwargs):
            prompts.append(kwargs["json"]["contents"][0]["parts"][0]["text"])
            return GoodResponse()
    monkeypatch.setattr(api.httpx,"AsyncClient",FakeClient)
    result=client.post(f"/api/ai/plan/{eid}",json={"note":"Twenty friends, one indoor volleyball court"})
    assert result.status_code==200,result.text
    data=result.json()
    assert data["requires_approval"] is True
    assert data["event_id"]==eid
    assert data["source"]=="gemini"
    assert [t["title"] for t in data["tasks"]]==[
        "Arrange volleyball nets","Check court lighting","Share arrival instructions"
    ]
    assert len(data["expected_signature"])==64
    assert "Alex" not in prompts[0] # no participant names added by CircleSplit
    assert "Confirm venue" in prompts[0]
    # Configured status changed because the test installed a fake API key;
    # the database event records must remain identical.
    assert client.get("/api/state").json()["events"] == before["events"]


def test_approved_ai_tasks_are_atomic_event_scoped_and_payment_safe(client):
    import app as api
    e = initial(client)
    eid=e["id"]
    with api.db() as conn:
        original_sig=api.task_list_signature(conn,eid)
    unchanged=client.get("/api/state").json()
    payload={"expected_signature":original_sig,
             "tasks":[{"title":"Arrange balls"},{"title":"Set up net"}]}
    result=client.post(f"/api/events/{eid}/tasks/bulk",json=payload)
    assert result.status_code==200,result.text
    assert result.json()["added"]==2
    assert result.json()["approvals_changed"] is False
    assert result.json()["payments_changed"] is False
    new_state=initial(client)
    assert len(new_state["tasks"])==2
    assert new_state["people"]==e["people"]
    assert new_state["total_cents"]==e["total_cents"]
    assert new_state["sandbox_cents"]==0
    assert new_state["simulated_cents"]==0
    # Previous draft is stale; no extra tasks should be inserted.
    assert client.post(f"/api/events/{eid}/tasks/bulk",json=payload).status_code==409
    assert len(initial(client)["tasks"])==2
    with api.db() as conn: current_sig=api.task_list_signature(conn,eid)
    invalid={"expected_signature":current_sig,
             "tasks":[{"title":"Fresh"},{"title":"fRESH"}]}
    assert client.post(f"/api/events/{eid}/tasks/bulk",json=invalid).status_code==422
    assert len(initial(client)["tasks"])==2
    # Task planning stays possible after a simulated contribution.
    pid=e["people"][0]["id"]
    client.post(f"/api/events/{eid}/people/{pid}/approve")
    client.post(f"/api/events/{eid}/people/{pid}/simulate")
    with api.db() as conn: sig=api.task_list_signature(conn,eid)
    approved=client.post(f"/api/events/{eid}/tasks/bulk",json={
        "expected_signature":sig,"tasks":[{"title":"Confirm final attendance"}]
    })
    assert approved.status_code==200,approved.text
    assert initial(client)["simulated_cents"]==1100
    assert len(initial(client)["tasks"])==3
    assert unchanged["events"][0]["tasks"]==[]


def test_ai_task_proposal_rejects_stale_checklist_and_conflicts(client):
    import app as api
    e=initial(client);eid=e["id"]
    with api.db() as conn: sig=api.task_list_signature(conn,eid)
    assert client.post(f"/api/events/{eid}/tasks",json={"title":"Book court"}).status_code==200
    assert client.post(f"/api/events/{eid}/tasks/bulk",json={
        "expected_signature":sig,"tasks":[{"title":"Arrange equipment"}]
    }).status_code==409
    with api.db() as conn: latest=api.task_list_signature(conn,eid)
    assert client.post(f"/api/events/{eid}/tasks/bulk",json={
        "expected_signature":latest,"tasks":[{"title":"book COURT"}]
    }).status_code==409
    assert len(initial(client)["tasks"])==1


def test_ai_plan_is_protected_and_unavailable_without_key(client,monkeypatch):
    e=initial(client);eid=e["id"]
    assert client.post(f"/api/ai/plan/{eid}",json={}).status_code==503
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","valid-long-owner-password")
    assert client.post(f"/api/ai/plan/{eid}",json={}).status_code==401
    assert client.post(f"/api/events/{eid}/tasks/bulk",json={
        "expected_signature":"a"*64,"tasks":[{"title":"Fake approval"}]
    }).status_code==401


def test_ai_task_provider_fails_safely_on_bad_output(client,monkeypatch):
    import app as api
    eid=initial(client)["id"]
    monkeypatch.setenv("GEMINI_API_KEY","fake-fixture-key")
    class BadResponse:
        def raise_for_status(self): pass
        def json(self):
            return {"candidates":[{"content":{"parts":[{"text":"{\"not_tasks\":[]}" }]}}]}
    class FakeClient:
        def __init__(self,*args,**kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self,*args): pass
        async def post(self,*args,**kwargs): return BadResponse()
    monkeypatch.setattr(api.httpx,"AsyncClient",FakeClient)
    r=client.post(f"/api/ai/plan/{eid}",json={})
    assert r.status_code==502
    assert "task list" in r.json()["detail"]
    assert initial(client)["tasks"]==[]


def test_participant_rsvp_changes_attendance_not_money_or_other_people(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    invitation=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    headers={"Authorization":"Bearer "+invitation}
    before=initial(client)
    # Participant can decline without changing budgets or other people's shares.
    declined=client.post("/api/participant/rsvp",headers=headers,json={"status":"declined"})
    assert declined.status_code==200,declined.text
    assert declined.json()["approved"] is False
    assert declined.json()["payment_changed"] is False
    assert client.get("/api/participant/overview",headers=headers).json()["rsvp_status"]=="declined"
    declined_state=initial(client)
    assert declined_state["total_cents"]==before["total_cents"]
    assert declined_state["expenses"]==before["expenses"]
    assert declined_state["people"][0]["share_cents"]==before["people"][0]["share_cents"]
    assert declined_state["people"][1:]==before["people"][1:]
    assert client.post("/api/participant/approve",headers=headers).status_code==409
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==409
    monkeypatch.setattr(paypal,"configured",lambda: True)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==409
    # Returning to attendance does not auto-approve, but explicitly approving does.
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"going"}).status_code==200
    assert client.post("/api/participant/approve",headers=headers).status_code==200
    assert initial(client)["people"][0]["approval_source"]=="participant_link"
    assert initial(client)["people"][0]["rsvp_status"]=="going"
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"maybe"}).status_code==200


def test_declining_rsvp_revokes_unpaid_approval_but_never_refunds(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    headers={"Authorization":"Bearer "+token}
    assert client.post("/api/participant/approve",headers=headers).status_code==200
    assert initial(client)["people"][0]["approved"]==1
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"declined"}).status_code==200
    assert initial(client)["people"][0]["approved"]==0
    assert initial(client)["people"][0]["approval_source"]==""
    # A new invitation may be issued only before payments are recorded.
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"going"}).status_code==200
    assert client.post("/api/participant/approve",headers=headers).status_code==200
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code==200
    amount=initial(client)["simulated_cents"]
    response=client.post("/api/participant/rsvp",headers=headers,json={"status":"declined"})
    assert response.status_code==200
    assert response.json()["payment_changed"] is False
    assert "refund" in response.json()["warning"]
    assert initial(client)["simulated_cents"]==amount
    assert initial(client)["people"][0]["status"]=="demo_paid"


def test_rsvp_invitation_expiry_scoping_and_authentication(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","test-owner-long-secret-for-hosted")
    headers={"Authorization":"Bearer "+token}
    assert client.post("/api/participant/rsvp",json={"status":"going"}).status_code==401
    assert client.get("/api/participant/rsvp",headers=headers).status_code==401
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"pending"}).status_code==422
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"going"}).status_code==200
    assert client.post("/api/events/1/people/1/approve",headers=headers).status_code==401
    assert client.get("/api/state",headers=headers).status_code==401
    assert client.get("/api/participant/overview",headers=headers).headers["cache-control"]=="no-store"
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"maybe"}).headers["referrer-policy"]=="no-referrer"
    assert client.post(f"/api/events/{eid}/people/{pid}/invite/revoke",auth=("judge","test-owner-long-secret-for-hosted")).status_code==200
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"maybe"}).status_code==404


def test_event_history_financial_integrity_and_privacy(client):
    """History records successful changes without leaking names, secrets or IDs."""
    import app as api
    e=initial(client)
    eid=e["id"]
    path=f"/api/events/{eid}/history"
    fresh=client.get(path)
    assert fresh.status_code==200
    assert fresh.json()["entries"]==[]  # pre-feature seed is not backfilled
    assert fresh.json()["integrity"]["status"]=="consistent"
    assert fresh.json()["integrity"]["checks"]["budget_cents"]==22000
    assert fresh.json()["integrity"]["checks"]["allocated_cents"]==22000
    assert fresh.json()["integrity"]["checks"]["verified_captures"]==0
    assert client.post(f"/api/events/{eid}/expenses",json={
        "title":"CONFIDENTIAL-EXPENSE-SENTINEL","amount":"2.00"
    }).status_code==200
    data=client.get(path).json()
    assert data["total_actions"]==1
    assert data["entries"][0]["action"]=="expense_added"
    assert data["entries"][0]["details"]=={"amount_cents":200,"category":"other"}
    assert data["integrity"]["status"]=="consistent"
    assert "CONFIDENTIAL-EXPENSE-SENTINEL" not in str(data)
    assert "Alex" not in str(data)
    assert "API_KEY" not in str(data)
    count=data["total_actions"]
    assert client.delete(f"/api/events/{eid}/expenses/9999999").status_code==404
    assert client.get(path).json()["total_actions"]==count
    new=client.post("/api/events",json={
        "name":"New fictional event", "date":"2026-11-19"
    })
    assert new.status_code==200
    new_id=new.json()["id"]
    created=client.get(f"/api/events/{new_id}/history").json()
    assert len(created["entries"])==1
    assert created["entries"][0]["action"]=="event_created"
    # Event history stays separated by event ID.
    assert all(entry["action"]=="event_created" for entry in created["entries"])


def test_history_tracks_private_approval_and_rsvp_without_exposing_bearer(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    path=f"/api/events/{eid}/history"
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    headers={"Authorization":"Bearer "+token}
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"going"}).status_code==200
    assert client.post("/api/participant/rsvp",headers=headers,json={"status":"going"}).status_code==200
    assert client.post("/api/participant/approve",headers=headers).status_code==200
    assert client.post("/api/participant/approve",headers=headers).status_code==200
    history=client.get(path).json()
    actions=[x["action"] for x in history["entries"]]
    assert actions.count("invitation_rotated")==1
    assert actions.count("participant_rsvp")==1
    assert actions.count("participant_approved")==1
    assert all(x["actor"]=="participant_link" for x in history["entries"]
               if x["action"] in ("participant_rsvp","participant_approved"))
    assert token not in str(history)
    assert "Alex" not in str(history)
    assert client.get(path).json()["integrity"]["status"]=="consistent"


def test_history_tracks_one_verified_capture_and_no_duplicate_webhook(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    client.post(f"/api/events/{eid}/people/{pid}/approve")
    monkeypatch.setattr(paypal,"configured",lambda:True)
    order_id="TEST-HISTORY-ORDER"
    async def fake_order(*args):
        return {"id":order_id,"approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=FAKE"}
    async def fake_capture(*args):
        return {"purchase_units":[{"payments":{"captures":[{
            "id":"FAKE-CAPTURE-SECRET","status":"COMPLETED",
            "amount":{"currency_code":"USD","value":f"{e['people'][0]['share_cents']/100:.2f}"},
        }]}}]}
    async def verified_webhook(*args): return True
    monkeypatch.setattr(paypal,"order",fake_order)
    monkeypatch.setattr(paypal,"capture",fake_capture)
    monkeypatch.setattr(paypal,"verify_webhook",verified_webhook)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==200
    path=f"/api/events/{eid}/history"
    created=client.get(path).json()
    assert created["integrity"]["checks"]["pending_orders"]==1
    assert created["integrity"]["checks"]["verified_captures"]==0
    assert client.post("/api/paypal/capture",json={"order_id":order_id}).status_code==200
    assert client.post("/api/paypal/capture",json={"order_id":order_id}).json()["already_recorded"] is True
    webhook={"id":"WEBHOOK-HISTORY-1","event_type":"PAYMENT.CAPTURE.COMPLETED",
             "resource":{"id":"FAKE-CAPTURE-SECRET","status":"COMPLETED",
                "amount":{"currency_code":"USD","value":"11.00"},
                "supplementary_data":{"related_ids":{"order_id":order_id}}}}
    assert client.post("/api/paypal/webhook",json=webhook).status_code==200
    assert client.post("/api/paypal/webhook",json=webhook).json()["duplicate"] is True
    history=client.get(path).json()
    codes=[x["action"] for x in history["entries"]]
    assert codes.count("sandbox_order_started")==1
    assert codes.count("sandbox_order_created")==1
    assert codes.count("sandbox_capture_verified")==1
    assert history["integrity"]["status"]=="consistent"
    assert history["integrity"]["checks"]["verified_captures"]==1
    assert history["integrity"]["checks"]["pending_orders"]==0
    assert order_id not in str(history)
    assert "FAKE-CAPTURE-SECRET" not in str(history)
    assert "WEBHOOK-HISTORY-1" not in str(history)


def test_integrity_detects_corrupted_allocations_and_payment_state(client):
    import app as api
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    with api.db() as conn:
        conn.execute("UPDATE people SET share_cents=share_cents+1 WHERE id=?",(pid,))
    report=client.get(f"/api/events/{eid}/history").json()
    assert report["integrity"]["status"]=="needs_review"
    assert "allocation_mismatch" in [x["code"] for x in report["integrity"]["issues"]]
    assert report["integrity"]["checks"]["allocated_cents"]==22001
    # Even if the demo database is inconsistent, checking it never mutates it.
    same=client.get(f"/api/events/{eid}/history").json()
    assert same["integrity"]==report["integrity"]


def test_history_scope_and_hosted_auth(client,monkeypatch):
    eid=initial(client)["id"]
    assert client.get(f"/api/events/987654/history").status_code==404
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_USERNAME","judge")
    monkeypatch.setenv("DEMO_PASSWORD","long-protected-demo-credentials")
    assert client.get(f"/api/events/{eid}/history").status_code==401
    assert client.get(f"/api/events/{eid}/history",
                      auth=("judge","long-protected-demo-credentials")).status_code==200
    assert client.get("/api/events/987654/history",
                      auth=("judge","long-protected-demo-credentials")).status_code==404
    token="a"*43
    assert client.get(f"/api/events/{eid}/history",
                      headers={"Authorization":"Bearer "+token}).status_code==401


def test_integrity_finds_unverified_sandbox_status_without_leaking_ids(client):
    import app as api
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    with api.db() as conn:
        conn.execute("UPDATE people SET status='sandbox_paid' WHERE id=?",(pid,))
    report=client.get(f"/api/events/{eid}/history").json()
    assert report["integrity"]["status"]=="needs_review"
    assert "paid_without_capture" in [x["code"] for x in report["integrity"]["issues"]]


def test_verified_sandbox_total_never_trusts_member_status_alone(client):
    """A participant status flag is not proof of a PayPal capture."""
    import app as api
    e=initial(client)
    eid=e["id"]
    pid=e["people"][0]["id"]
    with api.db() as conn:
        conn.execute("UPDATE people SET status='sandbox_paid' WHERE id=?",(pid,))
    state=initial(client)
    assert state["sandbox_cents"]==0
    report=client.get(f"/api/events/{eid}/history").json()
    assert "paid_without_capture" in [x["code"] for x in report["integrity"]["issues"]]


def test_verified_sandbox_total_counts_only_completed_capture_records(client):
    """Pending and incomplete sandbox payment rows cannot inflate confirmed totals."""
    import app as api
    e=initial(client)
    eid=e["id"]
    people=e["people"]
    first,second=people[0],people[1]
    with api.db() as conn:
        conn.execute(
            """INSERT INTO payments(event_id,person_id,amount_cents,request_id,capture_key,
                                    order_id,status,capture_id,created)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (eid,first["id"],first["share_cents"],"req-safe-1","cap-safe-1",
             "ORDER-PENDING","created",None,api.now())
        )
        assert conn.execute("SELECT changes()").fetchone()[0]==1
    assert initial(client)["sandbox_cents"]==0
    with api.db() as conn:
        conn.execute(
            """UPDATE payments SET status='completed',capture_id='VERIFIED-TEST-CAPTURE'
               WHERE person_id=?""", (first["id"],)
        )
    assert initial(client)["sandbox_cents"]==first["share_cents"]
    with api.db() as conn:
        conn.execute(
            """INSERT INTO payments(event_id,person_id,amount_cents,request_id,capture_key,
                                    order_id,status,created)
               VALUES(?,?,?,?,?,?,?,?)""",
            (eid,second["id"],second["share_cents"],"req-safe-2","cap-safe-2",
             "ORDER-NOCAPTURE","created",api.now())
        )
        conn.execute("UPDATE payments SET status='completed' WHERE person_id=?",
                     (second["id"],))
    assert initial(client)["sandbox_cents"]==first["share_cents"]


def test_expense_categories_totals_and_clone(client):
    event=initial(client);eid=event["id"]
    endpoint=f"/api/events/{eid}/budget-breakdown"
    report=client.get(endpoint)
    assert report.status_code==200,report.text
    data=report.json()
    assert data["source"]=="planned_expenses"
    assert data["total_cents"]==22000
    by_key={x["key"]:x for x in data["categories"]}
    assert by_key["venue"]["cents"]==16000
    assert by_key["equipment"]["cents"]==2500
    assert by_key["food"]["cents"]==3500
    assert sum(x["cents"] for x in data["categories"])==22000
    assert [x["category"] for x in event["expenses"]]==["venue","equipment","food"]
    copied=client.post(f"/api/events/{eid}/clone",json={"name":"Same event next week"})
    assert copied.status_code==200,copied.text
    target=next(e for e in client.get("/api/state").json()["events"] if e["id"]==copied.json()["id"])
    assert [(x["title"],x["cents"],x["category"]) for x in target["expenses"]]==[
        (x["title"],x["cents"],x["category"]) for x in event["expenses"]
    ]
    assert target["sandbox_cents"]==0
    assert all(p["approved"]==0 for p in target["people"])


def test_category_edit_is_metadata_only_until_budget_locked(client):
    event=initial(client);eid=event["id"];pid=event["people"][0]["id"]
    expense=event["expenses"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    before=initial(client)
    path=f"/api/events/{eid}/expenses/{expense}/category"
    response=client.patch(path,json={"category":"travel"})
    assert response.status_code==200,response.text
    assert response.json()["amount_changed"] is False
    after=initial(client)
    assert after["expenses"][0]["category"]=="travel"
    assert after["expenses"][0]["cents"]==before["expenses"][0]["cents"]
    assert after["people"]==before["people"]
    assert after["total_cents"]==before["total_cents"]
    assert client.get(f"/api/events/{eid}/history").json()["entries"][0]["action"]=="expense_recategorized"
    assert client.patch(path,json={"category":"travel"}).json()["changed"] is False
    assert client.patch(path,json={"category":"not-a-category"}).status_code==422
    assert client.patch(f"/api/events/{eid}/expenses/999999/category",json={"category":"food"}).status_code==404
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code==200
    assert client.patch(path,json={"category":"venue"}).status_code==409
    assert initial(client)["expenses"][0]["category"]=="travel"


def test_categorized_manual_and_ai_reviewed_bulk_expenses(client):
    event=client.post("/api/events",json={"name":"Conference meet-up","date":"2026-11-20"}).json()
    eid=event["id"]
    r=client.post(f"/api/events/{eid}/expenses",json={
        "title":"Taxi","amount":"12.15","category":"travel"
    })
    assert r.status_code==200,r.text
    assert client.post(f"/api/events/{eid}/expenses",json={
        "title":"Wrong","amount":"1.00","category":"chemicals"
    }).status_code==422
    bulk=client.post(f"/api/events/{eid}/expenses/bulk",json={"expenses":[
        {"title":"Food","amount":"7.85","category":"food"},
        {"title":"General expense","amount":"5.00"},
    ]})
    assert bulk.status_code==200,bulk.text
    r=client.get(f"/api/events/{eid}/budget-breakdown").json()
    assert r["total_cents"]==2500
    assert {x["key"]:x["cents"] for x in r["categories"]}=={
        "venue":0,"equipment":0,"food":785,
        "travel":1215,"services":0,"other":500
    }
    current=next(x for x in client.get("/api/state").json()["events"] if x["id"]==eid)
    assert [x["category"] for x in current["expenses"]]==["travel","food","other"]


def test_gemini_expense_category_suggestions_are_validated(client,monkeypatch):
    import app as api
    async def fake_provider(prompt):
        return {"expenses":[
            {"title":"Court","amount":"80.00","category":"venue"},
            {"title":"Mystery charge","amount":"2.00","category":"unsupported"},
            {"title":"Other","amount":"3.00"}
        ],"strategy":"equal","rationale":"Estimate only"}
    monkeypatch.setattr(api,"gemini_structured",fake_provider)
    proposal=client.post("/api/ai/parse",json={
        "note":"Court booking $80, mystery $2, incidental $3 to be reviewed."
    })
    assert proposal.status_code==200,proposal.text
    assert [x["category"] for x in proposal.json()["expenses"]]==["venue","other","other"]
    assert proposal.json()["requires_approval"] is True


def test_legacy_database_adds_category_without_losing_expenses(client,monkeypatch,tmp_path):
    import app as api
    import sqlite3
    legacy=tmp_path/"existing_legacy.sqlite3"
    with sqlite3.connect(str(legacy)) as conn:
        conn.executescript("""
            CREATE TABLE events(
                id INTEGER PRIMARY KEY,name TEXT NOT NULL,date TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',strategy TEXT NOT NULL DEFAULT 'equal',
                created TEXT NOT NULL
            );
            CREATE TABLE expenses(
                id INTEGER PRIMARY KEY,event_id INTEGER NOT NULL REFERENCES events(id),
                title TEXT NOT NULL,cents INTEGER NOT NULL
            );
        """)
        conn.execute("INSERT INTO events(id,name,date,note,created) VALUES(1,'Older event','2026-09-20','Past demo','2026-09-01')")
        conn.execute("INSERT INTO expenses(event_id,title,cents) VALUES(1,'Legacy venue',2500)")
    monkeypatch.setattr(api,"DB",legacy)
    api.initialize()
    with api.db() as conn:
        expense=conn.execute("SELECT title,cents,category FROM expenses WHERE event_id=1").fetchone()
        assert (expense["title"],expense["cents"],expense["category"])==("Legacy venue",2500,"other")
    api.initialize()  # Repeat is safe.
    with api.db() as conn:
        assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0]==1


def test_budget_breakdown_requires_organizer_access(client,monkeypatch):
    eid=initial(client)["id"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","category-test-password-long-enough")
    assert client.get(f"/api/events/{eid}/budget-breakdown").status_code==401
    assert client.patch(f"/api/events/{eid}/expenses/1/category",json={"category":"venue"}).status_code==401
    auth=("judge","category-test-password-long-enough")
    assert client.get(f"/api/events/{eid}/budget-breakdown",auth=auth).status_code==200


def test_budget_target_rounding_and_risk_warning(client):
    event=initial(client);eid=event["id"]
    assert event["planning"]["status"]=="no_ceiling"
    assert event["planning"]["projected_cents"]==22000
    assert client.get(f"/api/events/{eid}/planning").json()==event["planning"]
    response=client.put(f"/api/events/{eid}/planning",json={
        "ceiling":"230.00","reserve_percent":10
    })
    assert response.status_code==200,response.text
    p=response.json()["planning"]
    assert p["planned_cents"]==22000
    assert p["reserve_cents"]==2200
    assert p["projected_cents"]==24200
    assert p["headroom_cents"]==-1200
    assert p["over_ceiling_cents"]==1200
    assert p["status"]=="over_ceiling"
    after=initial(client)
    assert after["planning"]==p
    assert after["total_cents"]==event["total_cents"]
    assert after["people"]==event["people"]
    assert response.json()["financial_records_changed"] is False
    history=client.get(f"/api/events/{eid}/history").json()
    assert history["entries"][0]["action"]=="planning_target_updated"
    assert history["entries"][0]["details"]=={
        "ceiling_cents":23000,"reserve_percent":10
    }
    again=client.put(f"/api/events/{eid}/planning",json={
        "ceiling":"230.00","reserve_percent":10
    })
    assert again.status_code==200 and again.json()["changed"] is False
    assert client.get(f"/api/events/{eid}/history").json()["total_actions"]==1


def test_contingency_is_a_projection_not_a_payment_or_allocation(client):
    event=initial(client);eid=event["id"];pid=event["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    before=initial(client)
    p=client.put(f"/api/events/{eid}/planning",json={
        "ceiling":"225.00","reserve_percent":5
    })
    assert p.status_code==200
    assert p.json()["planning"]["status"]=="over_ceiling"
    assert p.json()["planning"]["reserve_cents"]==1100
    after=initial(client)
    assert after["people"]==before["people"]
    assert after["sandbox_cents"]==before["sandbox_cents"]==0
    assert after["simulated_cents"]==before["simulated_cents"]==0
    assert after["expenses"]==before["expenses"]
    # Existing private invitation and approval remain valid.
    assert client.get("/api/participant/overview",headers={
        "Authorization":"Bearer "+token
    }).status_code==200
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code==200
    assert client.put(f"/api/events/{eid}/planning",json={
        "ceiling":None,"reserve_percent":0
    }).status_code==200
    assert initial(client)["simulated_cents"]==1100


def test_risk_targets_are_advisory_and_update_after_expenses(client):
    event=client.post("/api/events",json={"name":"Team outing","date":"2026-11-17"}).json()
    eid=event["id"]
    client.put(f"/api/events/{eid}/planning",json={"ceiling":"30.00","reserve_percent":5})
    assert client.post(f"/api/events/{eid}/expenses",json={
        "title":"Room reservation","amount":"30.00"
    }).status_code==200
    planning=client.get(f"/api/events/{eid}/planning").json()
    assert planning["planned_cents"]==3000
    assert planning["reserve_cents"]==150
    assert planning["projected_cents"]==3150
    assert planning["status"]=="over_ceiling"
    # Going over an advisory cap must not automatically block budget edits.
    assert client.post(f"/api/events/{eid}/expenses",json={
        "title":"Extra equipment","amount":"2.00"
    }).status_code==200
    planning=client.get(f"/api/events/{eid}/planning").json()
    assert planning["planned_cents"]==3200
    assert planning["reserve_cents"]==160
    assert planning["over_ceiling_cents"]==360


def test_planning_settings_clone_without_payment_history(client):
    original=initial(client);eid=original["id"]
    assert client.put(f"/api/events/{eid}/planning",json={
        "ceiling":"300.00","reserve_percent":15
    }).status_code==200
    new=client.post(f"/api/events/{eid}/clone",json={"name":"Repeat meetup"})
    assert new.status_code==200,new.text
    assert new.json()["planning_copied"] is True
    duplicate=next(x for x in client.get("/api/state").json()["events"] if x["id"]==new.json()["id"])
    assert duplicate["planning"]["ceiling_cents"]==30000
    assert duplicate["planning"]["reserve_percent"]==15
    assert duplicate["planning"]["projected_cents"]==25300
    assert duplicate["sandbox_cents"]==0
    assert all(p["approved"]==0 for p in duplicate["people"])


def test_planning_validation_and_scope(client,monkeypatch):
    eid=initial(client)["id"]
    for ceiling in ["0","-1.00","1e4","NaN","100000.01","10.123"]:
        r=client.put(f"/api/events/{eid}/planning",json={
            "ceiling":ceiling,"reserve_percent":2
        })
        assert r.status_code==422,(ceiling,r.text)
    for percent in [-1,51,2.5]:
        assert client.put(f"/api/events/{eid}/planning",json={
            "ceiling":"100.00","reserve_percent":percent
        }).status_code==422
    assert client.put("/api/events/999999/planning",json={
        "ceiling":"50.00","reserve_percent":0
    }).status_code==404
    assert client.get("/api/events/999999/planning").status_code==404
    assert initial(client)["planning"]["status"]=="no_ceiling"
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","a-long-test-owner-password")
    assert client.get(f"/api/events/{eid}/planning").status_code==401
    assert client.put(f"/api/events/{eid}/planning",json={
        "ceiling":"100.00","reserve_percent":2
    }).status_code==401
    assert client.put(f"/api/events/{eid}/planning",json={
        "ceiling":"100.00","reserve_percent":2
    },auth=("judge","a-long-test-owner-password")).status_code==200


def test_planning_rounds_tiny_reserves_up_to_whole_cent(client):
    import app as api
    p=api.planning_forecast(101,110,5)
    assert p["reserve_cents"]==6
    assert p["projected_cents"]==107
    assert p["headroom_cents"]==3
    assert api.planning_forecast(0,None,0)["reserve_cents"]==0


def test_closeout_preview_remains_read_only_and_sandbox_only(client):
    e=initial(client);eid=e["id"]
    history_before=client.get(f"/api/events/{eid}/history").json()
    report=client.get(f"/api/events/{eid}/closeout")
    assert report.status_code==200,report.text
    d=report.json()
    assert d["event_id"]==eid and d["currency"]=="USD"
    assert d["mode"]=="SANDBOX ONLY"
    assert d["stage"]=="unverified"
    assert d["integrity"]["status"]=="consistent"
    assert d["summary"]["planned_cents"]==22000
    assert d["summary"]["allocated_cents"]==22000
    assert d["summary"]["verified_sandbox_cents"]==0
    assert d["summary"]["simulated_cents"]==0
    assert d["summary"]["unverified_against_sandbox_cents"]==22000
    assert d["summary"]["approvals_pending"]==20
    assert d["summary"]["pending_orders"]==0
    assert d["summary"]["participants"]==20
    assert len(d["participants"])==20
    assert all(p["pending_orders"]==0 for p in d["participants"])
    assert all(p["verified_sandbox_cents"]==0 for p in d["participants"])
    assert any("not real funds" in warning for warning in d["warnings"])
    assert "not a payment request" not in str(d).lower() or "not invoices" in str(d).lower()
    assert client.get(f"/api/events/{eid}/history").json()==history_before
    assert client.get(f"/api/events/{eid}/closeout").json()==d


def test_closeout_simulations_never_count_as_verified_sandbox(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code==200
    d=client.get(f"/api/events/{eid}/closeout").json()
    assert d["stage"]=="demo_activity"
    assert d["summary"]["simulated_cents"]==1100
    assert d["summary"]["verified_sandbox_cents"]==0
    assert d["summary"]["unverified_against_sandbox_cents"]==22000
    person=next(p for p in d["participants"] if p["name"]==e["people"][0]["name"])
    assert person["simulated_cents"]==1100
    assert person["verified_sandbox_cents"]==0
    assert person["unverified_against_sandbox_cents"]==1100
    assert person["recorded_status"]=="demo_paid"
    assert "paypal" not in person["approval_source"].lower()


def test_closeout_pending_orders_and_capture_references(client):
    import app as api
    e=initial(client);eid=e["id"];person=e["people"][0];pid=person["id"]
    with api.db() as c:
        c.execute(
            """INSERT INTO payments(event_id,person_id,amount_cents,request_id,capture_key,
                                    order_id,status,created)
               VALUES(?,?,?,?,?,?,?,?)""",
            (eid,pid,person["share_cents"],"closeout-created-1","closeout-cap-1",
             "FAKE-ORDER-SECRET-TEST","created",api.now())
        )
    pending=client.get(f"/api/events/{eid}/closeout").json()
    assert pending["stage"]=="orders_pending"
    assert pending["summary"]["pending_orders"]==1
    assert pending["summary"]["verified_sandbox_cents"]==0
    assert pending["participants"][0]["pending_orders"]==1
    assert pending["integrity"]["status"]=="consistent"
    assert "FAKE-ORDER-SECRET-TEST" not in str(pending)
    with api.db() as c:
        c.execute("""UPDATE payments SET status='completed',
                     capture_id='FAKE-CAPTURE-SECRET-TEST' WHERE person_id=?""",(pid,))
        c.execute("UPDATE people SET status='sandbox_paid' WHERE id=?",(pid,))
    captured=client.get(f"/api/events/{eid}/closeout").json()
    assert captured["summary"]["verified_sandbox_cents"]==person["share_cents"]
    assert captured["summary"]["pending_orders"]==0
    assert captured["summary"]["unverified_against_sandbox_cents"]==22000-person["share_cents"]
    assert captured["participants"][0]["verified_sandbox_cents"]==person["share_cents"]
    assert captured["participants"][0]["pending_orders"]==0
    assert captured["stage"]=="unverified"
    assert captured["integrity"]["status"]=="consistent"
    assert "FAKE-CAPTURE-SECRET-TEST" not in str(captured)


def test_closeout_can_describe_fully_captured_one_person_sandbox_event(client):
    import app as api
    event=client.post("/api/events",json={"name":"Solo group demo","date":"2026-11-22"}).json()
    eid=event["id"]
    assert client.post(f"/api/events/{eid}/people",json={"name":"Fictional Participant","weight":1}).status_code==200
    assert client.post(f"/api/events/{eid}/expenses",json={"title":"Rental fee","amount":"15.00"}).status_code==200
    e=next(x for x in client.get("/api/state").json()["events"] if x["id"]==eid)
    pid=e["people"][0]["id"]
    with api.db() as c:
        c.execute(
            """INSERT INTO payments(event_id,person_id,amount_cents,request_id,capture_key,
                                    order_id,status,capture_id,created)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (eid,pid,1500,"closeout-solo-req","closeout-solo-cap",
             "CLOSEOUT-SOLO-ORDER","completed","CLOSEOUT-SOLO-CAPTURE",api.now())
        )
        c.execute("UPDATE people SET status='sandbox_paid' WHERE id=?",(pid,))
    d=client.get(f"/api/events/{eid}/closeout").json()
    assert d["stage"]=="sandbox_captures_cover_budget"
    assert d["summary"]["verified_sandbox_cents"]==1500
    assert d["summary"]["unverified_against_sandbox_cents"]==0
    assert d["integrity"]["status"]=="consistent"
    assert d["summary"]["pending_orders"]==0


def test_closeout_never_mistakes_corruption_for_complete_settlement(client):
    import app as api
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    with api.db() as c:
        c.execute("UPDATE people SET share_cents=share_cents+1 WHERE id=?",(pid,))
    d=client.get(f"/api/events/{eid}/closeout").json()
    assert d["stage"]=="needs_review"
    assert d["integrity"]["status"]=="needs_review"
    assert "allocation_mismatch" in [x["code"] for x in d["integrity"]["issues"]]
    assert d["summary"]["allocated_cents"]==22001


def test_closeout_protected_from_public_or_participant_invitation(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","long-closeout-test-owner-password")
    assert client.get(f"/api/events/{eid}/closeout").status_code==401
    assert client.get(f"/api/events/{eid}/closeout",
                      headers={"Authorization":"Bearer "+token}).status_code==401
    authorized=client.get(f"/api/events/{eid}/closeout",
                          auth=("judge","long-closeout-test-owner-password"))
    assert authorized.status_code==200
    assert authorized.json()["event_id"]==eid
    assert client.get("/api/events/999999/closeout",
                      auth=("judge","long-closeout-test-owner-password")).status_code==404


def test_recovery_queue_is_read_only_and_requires_organizer(client,monkeypatch):
    import app as api
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    before=client.get("/api/state").json()
    data=client.get("/api/paypal/recovery")
    assert data.status_code==200,data.text
    assert data.json()["mode"]=="PAYPAL_SANDBOX"
    assert data.json()["total_records"]==0
    assert data.json()["items"]==[]
    assert client.get("/api/state").json()==before

    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","strong-recovery-owner-password")
    assert client.get("/api/paypal/recovery").status_code==401
    assert client.get("/api/paypal/recovery",headers={
        "Authorization":"Bearer "+token
    }).status_code==401
    assert client.get("/api/paypal/recovery",
        auth=("judge","strong-recovery-owner-password")).status_code==200


def test_failed_creation_stays_locked_and_is_visible_for_manual_review(client,monkeypatch):
    from fastapi import HTTPException
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    count=[]
    async def ambiguous_order(*args):
        count.append(args)
        raise HTTPException(502,"PayPal sandbox request failed")
    monkeypatch.setattr(paypal,"order",ambiguous_order)
    failed=client.post(f"/api/paypal/orders/{eid}/{pid}")
    assert failed.status_code==502
    assert len(count)==1
    report=client.get("/api/paypal/recovery").json()
    assert report["total_records"]==1
    assert report["summary"]["creating"]==1
    item=report["items"][0]
    assert item["status"]=="creating"
    assert item["action"]=="manual_review"
    assert item["order_id"] is None
    assert "do not create another" in item["explanation"]
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==409
    assert len(count)==1
    assert initial(client)["sandbox_cents"]==0
    assert client.get(f"/api/events/{eid}/closeout").json()["summary"]["pending_orders"]==1


def test_capture_timeout_stays_locked_until_existing_order_is_reconciled(client,monkeypatch):
    from fastapi import HTTPException
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    amount=e["people"][0]["share_cents"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    async def fake_order(*args):
        return {"id":"SAFE-RECOVERY-ORDER-9",
                "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=X"}
    monkeypatch.setattr(paypal,"order",fake_order)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==200
    captures=[]
    async def failed_capture(*args):
        captures.append(args)
        import app as api
        with api.db() as conn:
            assert conn.execute(
                "SELECT status FROM payments WHERE order_id='SAFE-RECOVERY-ORDER-9'"
            ).fetchone()["status"]=="capturing"
        raise HTTPException(502,"PayPal sandbox request failed")
    monkeypatch.setattr(paypal,"capture",failed_capture)
    first=client.post("/api/paypal/capture",json={"order_id":"SAFE-RECOVERY-ORDER-9"})
    assert first.status_code==502
    again=client.post("/api/paypal/capture",json={"order_id":"SAFE-RECOVERY-ORDER-9"})
    assert again.status_code==409
    assert len(captures)==1
    recovery=client.get("/api/paypal/recovery").json()
    assert recovery["summary"]["capturing"]==1
    assert recovery["items"][0]["action"]=="check_existing_order"
    assert recovery["items"][0]["order_id"]=="SAFE-RECOVERY-ORDER-9"
    assert initial(client)["sandbox_cents"]==0

    async def fake_details(order_id):
        return {
            "id":order_id,"intent":"CAPTURE","status":"APPROVED",
            "purchase_units":[{"custom_id":f"{eid}:{pid}",
               "amount":{"currency_code":"USD","value":f"{amount/100:.2f}"}}],
        }
    monkeypatch.setattr(paypal,"details",fake_details)
    check=client.post("/api/paypal/order-status/SAFE-RECOVERY-ORDER-9")
    assert check.status_code==200
    assert check.json()["action"]=="pending"
    assert check.json()["verified"] is False
    assert len(captures)==1

    async def completed_details(order_id):
        result=await fake_details(order_id)
        result["status"]="COMPLETED"
        result["purchase_units"][0]["payments"]={"captures":[{
          "id":"SAFE-RECOVERY-CAPTURE-1","status":"COMPLETED",
          "amount":{"currency_code":"USD","value":f"{amount/100:.2f}"}
        }]}
        return result
    monkeypatch.setattr(paypal,"details",completed_details)
    result=client.post("/api/paypal/order-status/SAFE-RECOVERY-ORDER-9")
    assert result.status_code==200,result.text
    assert result.json()["verified"] is True
    assert result.json()["action"]=="done"
    assert len(captures)==1
    assert initial(client)["sandbox_cents"]==amount
    assert client.get("/api/paypal/recovery").json()["summary"]["completed"]==1
    history=client.get(f"/api/events/{eid}/history").json()
    assert sum(x["action"]=="sandbox_capture_verified" for x in history["entries"])==1
    assert client.post("/api/paypal/capture",json={"order_id":"SAFE-RECOVERY-ORDER-9"}).json()["already_recorded"] is True


def test_completed_payment_without_capture_id_fails_closed(client):
    import app as api
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    with api.db() as conn:
        conn.execute(
            """INSERT INTO payments(event_id,person_id,amount_cents,request_id,capture_key,
               order_id,status,created) VALUES(?,?,?,?,?,?,?,?)""",
            (eid,pid,1100,"invalid-rec-req","invalid-rec-cap",
             "CLOSED-ORDER-MISSING-CAP","completed",api.now())
        )
    assert client.post("/api/paypal/capture",json={
        "order_id":"CLOSED-ORDER-MISSING-CAP"
    }).status_code==409
    assert client.post("/api/paypal/order-status/CLOSED-ORDER-MISSING-CAP").status_code==409
    report=client.get("/api/paypal/recovery").json()
    assert report["summary"]["completed"]==1
    assert report["items"][0]["action"]=="manual_review"
    assert report["items"][0]["order_id"] is None


def test_paypal_order_redirect_refuses_external_untrusted_host(monkeypatch):
    import asyncio
    async def forged_api(*args):
        return {"id":"FORGED-ORDER", "links":[{"rel":"payer-action",
             "href":"https://paypal.com.evil.example/checkoutnow?token=steal"}]}
    monkeypatch.setattr(paypal,"api",forged_api)
    with pytest.raises(Exception) as error:
        asyncio.run(paypal.order(2500,1,2,
            "https://circlesplit-ai-demo.onrender.com/workspace?payment=return",
            "fixed-idempotency-key"))
    assert "trusted sandbox approval link" in str(error.value)
    assert paypal.approval_link({"links":[{"rel":"approve",
      "href":"https://www.sandbox.paypal.com/checkoutnow?token=VALID"}]})=="https://www.sandbox.paypal.com/checkoutnow?token=VALID"


def test_planning_backup_round_trip_creates_fresh_unpaid_events(client):
    import app as api
    original=initial(client);eid=original["id"];pid=original["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code==200
    invitation=client.post(f"/api/events/{eid}/people/{original['people'][1]['id']}/invite").json()["token"]
    assert client.post(f"/api/events/{eid}/tasks/starter").status_code==200
    assert client.put(f"/api/events/{eid}/planning",json={
        "ceiling":"300.00","reserve_percent":12
    }).status_code==200
    report=client.get("/api/planning-backup")
    assert report.status_code==200,report.text
    backup=report.json()
    assert backup["app"]=="CircleSplit AI"
    assert backup["kind"]=="planning-backup"
    assert backup["schema_version"]==1
    assert backup["currency"]=="USD"
    assert len(backup["events"])==1
    event=backup["events"][0]
    assert event["strategy"]=="equal"
    assert len(event["people"])==20
    assert len(event["expenses"])==3
    assert event["planning"]=={"ceiling_cents":30000,"reserve_percent":12}
    assert event["tasks"] and all(set(t)=={"title"} for t in event["tasks"])
    assert all(set(p)=={"name","weight"} for p in event["people"])
    assert all(set(x)=={"title","cents","category"} for x in event["expenses"])
    dumped=str(backup).lower()
    for forbidden in ["share_cents","approved","rsvp","order_id",
                      "capture_id","request_id","capture_key","simulated_cents"]:
        assert forbidden not in dumped
    assert invitation not in str(backup)
    restored=client.post("/api/planning-backup/restore",json=backup)
    assert restored.status_code==200,restored.text
    result=restored.json()
    assert result["restored_events"]==1
    assert result["payments_restored"] is False
    assert result["approvals_restored"] is False
    assert result["invitations_restored"] is False
    assert result["rsvp_restored"] is False
    assert result["tasks_reset"] is True
    new_id=result["created_event_ids"][0]
    assert new_id!=eid
    state=client.get("/api/state").json()["events"]
    source=next(x for x in state if x["id"]==eid)
    target=next(x for x in state if x["id"]==new_id)
    assert source["simulated_cents"]==1100
    assert source["people"][0]["status"]=="demo_paid"
    assert target["simulated_cents"]==0 and target["sandbox_cents"]==0
    assert target["total_cents"]==source["total_cents"]
    assert target["planning"]==source["planning"]
    assert all(p["approved"]==0 and p["status"]=="unpaid"
               and p["rsvp_status"]=="pending" for p in target["people"])
    assert sum(p["share_cents"] for p in target["people"])==target["total_cents"]
    assert all(not t["completed"] for t in target["tasks"])
    with api.db() as c:
        assert c.execute("SELECT COUNT(*) FROM payments WHERE event_id=?",(new_id,)).fetchone()[0]==0
        assert c.execute("""SELECT COUNT(*) FROM participant_invites
                           WHERE person_id IN (SELECT id FROM people WHERE event_id=?)""",(new_id,)).fetchone()[0]==0
    history=client.get(f"/api/events/{new_id}/history").json()
    assert history["entries"][0]["action"]=="planning_restored"
    assert history["entries"][0]["actor"]=="system"


def test_planning_restore_is_idempotent_even_if_export_time_changes(client):
    backup=client.get("/api/planning-backup").json()
    first=client.post("/api/planning-backup/restore",json=backup)
    assert first.status_code==200,first.text
    before=client.get("/api/state").json()["events"]
    backup["exported_at"]="2026-11-20T05:00:00+00:00"
    second=client.post("/api/planning-backup/restore",json=backup)
    assert second.status_code==409,second.text
    assert "already restored" in second.json()["detail"]
    assert client.get("/api/state").json()["events"]==before


@pytest.mark.parametrize("path,value",[
    (("events",0,"people",0,"approved"),True),
    (("events",0,"payments"),[{"amount_cents":1100}]),
    (("events",0,"expenses",0,"capture_id"),"forged"),
    (("events",0,"tasks",0,"completed"),True),
    (("events",0,"rsvp_status"),"going"),
    (("transactions",),[]),
])
def test_planning_restore_rejects_financial_or_unapproved_fields(client,path,value):
    backup=client.get("/api/planning-backup").json()
    if path[0]=="events" and "tasks" in path:
        assert client.post(f"/api/events/{initial(client)['id']}/tasks/starter").status_code==200
        backup=client.get("/api/planning-backup").json()
    current=backup
    for key in path[:-1]:
        current=current[key]
    current[path[-1]]=value
    before=client.get("/api/state").json()
    response=client.post("/api/planning-backup/restore",json=backup)
    assert response.status_code==422,response.text
    assert "unsupported fields" in response.json()["detail"]
    assert client.get("/api/state").json()==before


def test_planning_restore_rejects_invalid_amounts_dates_and_names_atomically(client):
    import copy
    original=client.get("/api/planning-backup").json()
    baseline=client.get("/api/state").json()
    mutations=[
        ("bad date", lambda b:b["events"][0].update({"date":"2026-02-30"})),
        ("negative amount", lambda b:b["events"][0]["expenses"][0].update({"cents":-1})),
        ("float cents", lambda b:b["events"][0]["expenses"][0].update({"cents":1.5})),
        ("bad currency", lambda b:b.update({"currency":"NOK"})),
        ("unsupported version", lambda b:b.update({"schema_version":2})),
        ("duplicate person", lambda b:b["events"][0]["people"][1].update(
            {"name":b["events"][0]["people"][0]["name"].upper()})),
        ("huge total", lambda b:b["events"][0]["expenses"].extend([
            {"title":"Huge extra","cents":10_000_000,"category":"other"}
        ])),
    ]
    for label,fn in mutations:
        backup=copy.deepcopy(original)
        fn(backup)
        r=client.post("/api/planning-backup/restore",json=backup)
        assert r.status_code==422,(label,r.text)
        assert client.get("/api/state").json()==baseline,(label,"unexpected mutation")


def test_restore_multiple_events_is_atomic_if_later_event_invalid(client):
    import copy
    backup=client.get("/api/planning-backup").json()
    clone=copy.deepcopy(backup["events"][0])
    clone["name"]="Second event with invalid date"
    clone["date"]="2026-13-99"
    backup["events"].append(clone)
    baseline=client.get("/api/state").json()
    res=client.post("/api/planning-backup/restore",json=backup)
    assert res.status_code==422
    assert client.get("/api/state").json()==baseline


def test_planning_backup_hosted_auth_and_participant_separation(client,monkeypatch):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    invitation=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    backup=client.get("/api/planning-backup").json()
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","owner-planning-backup-secret")
    assert client.get("/api/planning-backup").status_code==401
    assert client.post("/api/planning-backup/restore",json=backup).status_code==401
    assert client.get("/api/planning-backup",
        headers={"Authorization":"Bearer "+invitation}).status_code==401
    assert client.post("/api/planning-backup/restore",json=backup,
        headers={"Authorization":"Bearer "+invitation}).status_code==401
    owner=("judge","owner-planning-backup-secret")
    assert client.get("/api/planning-backup",auth=owner).status_code==200
    assert client.post("/api/planning-backup/restore",json=backup,auth=owner).status_code==200


def test_planning_backup_size_limit_and_schema_version(client):
    data=client.get("/api/planning-backup").json()
    huge=" "*700_100
    response=client.post("/api/planning-backup/restore",
        content=huge,headers={"Content-Type":"application/json"})
    assert response.status_code==413
    data["events"]=[]
    assert client.post("/api/planning-backup/restore",json=data).status_code==422


def test_quickstart_catalog_contains_valid_fictional_costs(client):
    catalog=client.get("/api/event-templates")
    assert catalog.status_code==200,catalog.text
    data=catalog.json()
    assert data["mode"]=="SANDBOX ONLY"
    assert data["currency"]=="USD"
    assert len(data["templates"])==5
    assert {t["key"] for t in data["templates"]}=={
        "volleyball","dinner","weekend-trip","study-meetup","community-cleanup"
    }
    assert all(t["estimated_cents"]==sum(x["cents"] for x in t["expenses"])
               for t in data["templates"])
    assert all(t["estimated_cents"]>0 and t["tasks"] for t in data["templates"])
    assert all(x["category"] in {
        "venue","equipment","food","travel","services","other"
    } for t in data["templates"] for x in t["expenses"])
    assert "no real prices" in data["notice"].lower()
    assert "payment records" in data["notice"].lower()


def test_quickstart_creates_atomic_event_with_checklist_and_no_people_or_money(client):
    original=initial(client)
    request_key="acdde001-1111-4222-8333-1234567890ab"
    response=client.post("/api/event-templates/volleyball/create",json={
        "name":"  My friends' volleyball  ","date":"2026-12-03",
        "include_expenses":True,"include_tasks":True,"request_key":request_key
    })
    assert response.status_code==200,response.text
    result=response.json()
    assert result["reused"] is False
    assert result["expense_count"]==3
    assert result["task_count"]==5
    assert result["estimated_cents"]==22000
    assert result["participants_created"]==0
    assert result["approvals_created"]==0
    assert result["payments_created"]==0
    eid=result["id"]
    event=next(e for e in client.get("/api/state").json()["events"] if e["id"]==eid)
    assert event["name"]=="My friends' volleyball"
    assert event["date"]=="2026-12-03"
    assert event["total_cents"]==22000
    assert event["strategy"]=="equal"
    assert not event["people"]
    assert event["approved"]==0
    assert event["sandbox_cents"]==0 and event["simulated_cents"]==0
    assert all(not task["completed"] for task in event["tasks"])
    assert [e["category"] for e in event["expenses"]]==["venue","equipment","food"]
    assert initial(client)["id"]==eid  # newest selected as first by API; source still exists
    state=client.get("/api/state").json()["events"]
    source=next(e for e in state if e["id"]==original["id"])
    assert source==original
    history=client.get(f"/api/events/{eid}/history").json()
    assert history["total_actions"]==1
    assert history["entries"][0]["action"]=="event_template_created"
    assert history["entries"][0]["details"]=={
        "template":"volleyball","expenses":3,"tasks":5
    }


def test_quickstart_can_create_task_only_plan_without_costs(client):
    response=client.post("/api/event-templates/study-meetup/create",json={
        "name":"Study circle","date":"2026-12-05",
        "include_expenses":False,"include_tasks":True,
        "request_key":"acdde002-1111-4222-8333-1234567890ab"
    })
    assert response.status_code==200,response.text
    result=response.json()
    assert result["expense_count"]==0
    assert result["estimated_cents"]==0
    event=next(e for e in client.get("/api/state").json()["events"] if e["id"]==result["id"])
    assert event["expenses"]==[]
    assert event["total_cents"]==0
    assert len(event["tasks"])==5
    assert event["people"]==[]


def test_quickstart_idempotency_key_replay_creates_no_duplicate_events(client):
    request={
        "name":"Weekend with friends","date":"2026-12-06",
        "include_expenses":True,"include_tasks":False,
        "request_key":"acdde003-1111-4222-8333-1234567890ab"
    }
    first=client.post("/api/event-templates/weekend-trip/create",json=request)
    assert first.status_code==200,first.text
    event_id=first.json()["id"]
    before=client.get("/api/state").json()["events"]
    same=client.post("/api/event-templates/weekend-trip/create",json=request)
    assert same.status_code==200,same.text
    assert same.json()["reused"] is True
    assert same.json()["id"]==event_id
    assert client.get("/api/state").json()["events"]==before
    changed=client.post("/api/event-templates/weekend-trip/create",json={
        **request,"name":"Different event"
    })
    assert changed.status_code==409,changed.text
    assert client.get("/api/state").json()["events"]==before
    another=client.post("/api/event-templates/weekend-trip/create",json={
        **request,"request_key":"acdde004-1111-4222-8333-1234567890ab"
    })
    assert another.status_code==200
    assert another.json()["id"]!=event_id


def test_quickstart_rejects_unknown_template_bad_date_or_extra_fields(client):
    payload={
        "name":"Test group","date":"2026-12-01",
        "include_expenses":True,"include_tasks":True,
        "request_key":"acdde005-1111-4222-8333-1234567890ab"
    }
    start=client.get("/api/state").json()["events"]
    assert client.post("/api/event-templates/missing/create",json=payload).status_code==404
    for date in ["2026-02-30","2026-13-01","2026/12/01","garbage"]:
        assert client.post("/api/event-templates/volleyball/create",json={
            **payload,"date":date
        }).status_code==422
    assert client.post("/api/event-templates/volleyball/create",json={
        **payload,"name":"  "
    }).status_code==422
    assert client.post("/api/event-templates/volleyball/create",json={
        **payload,"payments":[{"status":"completed"}]
    }).status_code==422
    assert client.post("/api/event-templates/volleyball/create",json={
        **payload,"request_key":"not-a-valid-idempotency-key"
    }).status_code==422
    assert client.get("/api/state").json()["events"]==start


def test_quickstart_creation_rolls_back_atomically_when_history_fails(client,monkeypatch):
    import app as api
    original=api.record_history
    def refuse_history(c,event_id,action,**kwargs):
        if action=="event_template_created":
            raise RuntimeError("simulated transaction failure")
        return original(c,event_id,action,**kwargs)
    monkeypatch.setattr(api,"record_history",refuse_history)
    start=client.get("/api/state").json()["events"]
    with pytest.raises(RuntimeError,match="simulated transaction failure"):
        client.post("/api/event-templates/dinner/create",json={
            "name":"Atomic rollback demo","date":"2026-12-09",
            "request_key":"acdde006-1111-4222-8333-1234567890ab"
        })
    assert client.get("/api/state").json()["events"]==start
    with api.db() as c:
        assert c.execute(
            "SELECT COUNT(*) FROM template_creations WHERE request_key=?",
            ("acdde006-1111-4222-8333-1234567890ab",)
        ).fetchone()[0]==0


def test_quickstart_auth_separates_invite_links_from_organizer(client,monkeypatch):
    person=initial(client)["people"][0];e=initial(client)
    invite=client.post(f"/api/events/{e['id']}/people/{person['id']}/invite").json()["token"]
    payload={"name":"Protected starter","date":"2026-12-10",
             "request_key":"acdde007-1111-4222-8333-1234567890ab"}
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","owner-secret-quickstart-demo")
    assert client.get("/api/event-templates").status_code==401
    assert client.post("/api/event-templates/volleyball/create",json=payload).status_code==401
    assert client.post("/api/event-templates/volleyball/create",json=payload,
        headers={"Authorization":"Bearer "+invite}).status_code==401
    auth=("judge","owner-secret-quickstart-demo")
    assert client.get("/api/event-templates",auth=auth).status_code==200
    assert client.post("/api/event-templates/volleyball/create",json=payload,
        auth=auth).status_code==200


def test_quickstart_does_not_reset_existing_sandbox_approvals(client):
    existing=initial(client);eid=existing["id"];pid=existing["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code==200
    before=next(e for e in client.get("/api/state").json()["events"] if e["id"]==eid)
    result=client.post("/api/event-templates/community-cleanup/create",json={
        "name":"Clean the park","date":"2026-12-12",
        "request_key":"acdde008-1111-4222-8333-1234567890ab"
    })
    assert result.status_code==200,result.text
    after=next(e for e in client.get("/api/state").json()["events"] if e["id"]==eid)
    assert after==before
    assert after["simulated_cents"]==1100


def test_edit_expense_updates_exact_cents_and_invalidates_prior_consent(client):
    e=initial(client);eid=e["id"];ex=e["expenses"][0];pid=e["people"][0]["id"]
    approved=client.post(f"/api/events/{eid}/people/{pid}/approve")
    assert approved.status_code==200,approved.text
    invitation=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    p=f"/api/events/{eid}/expenses/{ex['id']}"
    initial_share=e["people"][0]["share_cents"]
    response=client.put(p,json={
        "title":"  Updated court rental  ","amount":"165.01","category":"venue"
    })
    assert response.status_code==200,response.text
    assert response.json()["changed"] is True
    assert response.json()["approvals_reset"] is True
    now=initial(client)
    assert now["total_cents"]==22501
    assert sum(x["share_cents"] for x in now["people"])==22501
    assert now["people"][0]["share_cents"]!=initial_share
    assert all(not x["approved"] for x in now["people"])
    assert now["expenses"][0]["title"]=="Updated court rental"
    assert now["expenses"][0]["cents"]==16501
    assert client.get("/api/participant/overview",headers={
        "Authorization":"Bearer "+invitation
    }).status_code==404
    history=client.get(f"/api/events/{eid}/history").json()["entries"]
    assert history[0]["action"]=="expense_updated"
    assert history[0]["details"]["old_cents"]==16000
    assert history[0]["details"]["new_cents"]==16501
    assert "court rental" not in str(history).lower()
    assert invitation not in str(history)


def test_noop_expense_and_participant_edits_preserve_approvals_and_invites(client):
    e=initial(client);eid=e["id"];x=e["expenses"][0];p=e["people"][0]
    assert client.post(f"/api/events/{eid}/people/{p['id']}/approve").status_code==200
    token=client.post(f"/api/events/{eid}/people/{p['id']}/invite").json()["token"]
    event_history=client.get(f"/api/events/{eid}/history").json()["total_actions"]
    unchanged=client.put(f"/api/events/{eid}/expenses/{x['id']}",json={
        "title":x["title"],"amount":f"{x['cents']/100:.2f}","category":x["category"]
    })
    assert unchanged.status_code==200 and unchanged.json()["changed"] is False
    unchanged_p=client.put(f"/api/events/{eid}/people/{p['id']}",json={
        "name":p["name"],"weight":p["weight"]
    })
    assert unchanged_p.status_code==200 and unchanged_p.json()["changed"] is False
    assert initial(client)["approved"]==1
    assert client.get("/api/participant/overview",headers={
        "Authorization":"Bearer "+token
    }).status_code==200
    assert client.get(f"/api/events/{eid}/history").json()["total_actions"]==event_history


def test_edit_weight_and_name_recalculates_weighted_split(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/allocation",json={"strategy":"weighted"}).status_code==200
    response=client.put(f"/api/events/{eid}/people/{pid}",json={
        "name":"  New organizer  ","weight":3
    })
    assert response.status_code==200,response.text
    assert response.json()["shares_recalculated"] is True
    updated=initial(client)
    assert updated["people"][0]["name"]=="New organizer"
    assert updated["people"][0]["weight"]==3
    assert sum(x["share_cents"] for x in updated["people"])==updated["total_cents"]
    assert updated["people"][0]["share_cents"]>updated["people"][1]["share_cents"]
    assert client.get(f"/api/events/{eid}/history").json()["entries"][0]["action"]=="participant_updated"


def test_person_edit_resets_approval_and_invalidates_link(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    token=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    res=client.put(f"/api/events/{eid}/people/{pid}",json={"name":"Revised name","weight":2})
    assert res.status_code==200,res.text
    assert initial(client)["approved"]==0
    assert client.get("/api/participant/overview",headers={
        "Authorization":"Bearer "+token
    }).status_code==404


def test_edits_validate_input_and_do_not_partially_update(client):
    e=initial(client);eid=e["id"];expense=e["expenses"][0];person=e["people"][0]
    before=client.get("/api/state").json()
    for amt in ["-1","0","1.234","notmoney","100000.01"]:
        r=client.put(f"/api/events/{eid}/expenses/{expense['id']}",json={
            "title":"Court","amount":amt,"category":"venue"
        })
        assert r.status_code==422,(amt,r.text)
    for weight in [0,11,1.5]:
        r=client.put(f"/api/events/{eid}/people/{person['id']}",json={
            "name":"Revised name","weight":weight
        })
        assert r.status_code==422,(weight,r.text)
    r=client.put(f"/api/events/{eid}/people/{person['id']}",json={
        "name":e["people"][1]["name"],"weight":2
    })
    assert r.status_code==409,r.text
    assert client.put(f"/api/events/{eid}/expenses/999999",json={
        "title":"Court","amount":"50","category":"venue"
    }).status_code==404
    assert client.put(f"/api/events/{eid}/people/999999",json={
        "name":"Nobody","weight":2
    }).status_code==404
    assert client.get("/api/state").json()==before


def test_edits_blocked_after_sandbox_or_simulated_payment(client):
    e=initial(client);eid=e["id"];pid=e["people"][0]["id"];expense=e["expenses"][0]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code==200
    expense_r=client.put(f"/api/events/{eid}/expenses/{expense['id']}",json={
        "title":"Revised court","amount":"155.00","category":"venue"
    })
    person_r=client.put(f"/api/events/{eid}/people/{pid}",json={
        "name":"Revised participant","weight":3
    })
    assert expense_r.status_code==409
    assert person_r.status_code==409
    state=initial(client)
    assert state["expenses"]==e["expenses"]
    assert state["people"][0]["status"]=="demo_paid"
    assert state["people"][0]["weight"]==e["people"][0]["weight"]


def test_event_edit_endpoints_require_organizer_not_invitation(client,monkeypatch):
    e=initial(client);eid=e["id"];person=e["people"][0];ex=e["expenses"][0]
    invite=client.post(f"/api/events/{eid}/people/{person['id']}/invite").json()["token"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","secure-edit-test-owner-password")
    xp=f"/api/events/{eid}/expenses/{ex['id']}"
    pp=f"/api/events/{eid}/people/{person['id']}"
    expense_data={"title":"Court","amount":"40.00","category":"venue"}
    person_data={"name":"Revised test","weight":2}
    assert client.put(xp,json=expense_data).status_code==401
    assert client.put(pp,json=person_data).status_code==401
    assert client.put(xp,json=expense_data,headers={
        "Authorization":"Bearer "+invite
    }).status_code==401
    assert client.put(pp,json=person_data,headers={
        "Authorization":"Bearer "+invite
    }).status_code==401
    auth=("judge","secure-edit-test-owner-password")
    assert client.put(xp,json=expense_data,auth=auth).status_code==200
