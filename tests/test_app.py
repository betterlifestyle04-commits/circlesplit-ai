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
