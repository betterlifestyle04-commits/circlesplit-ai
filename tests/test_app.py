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
                    "approval_source","status","expires_at","currency","payment_mode","identity_verified"}
    assert d["participant"]=="Alex" and d["share_cents"]==1100
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
