"""Private participant share transparency and safe approval of reviewed amounts.

All tests are local; no PayPal calls, payment capture or live funds.
"""
import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch,tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB",str(tmp_path/"share-preview.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID",raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET",raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as c:
        yield c


def invitation(client):
    event=client.get("/api/state").json()["events"][0]
    eid=event["id"]
    person=event["people"][0]
    link=client.post(f"/api/events/{eid}/people/{person['id']}/invite")
    assert link.status_code==200,link.text
    return eid,person["id"],{"Authorization":"Bearer "+link.json()["token"]}


def overview(client,auth):
    response=client.get("/api/participant/overview",headers=auth)
    assert response.status_code==200,response.text
    return response.json()


def test_invited_participant_sees_aggregates_without_other_people(client):
    import app
    eid,pid,auth=invitation(client)
    private=overview(client,auth)
    breakdown=private["share_breakdown"]
    with app.db() as c:
        budget=c.execute("SELECT SUM(cents) FROM expenses WHERE event_id=?",(eid,)).fetchone()[0]
        count=c.execute("SELECT COUNT(*) FROM people WHERE event_id=?",(eid,)).fetchone()[0]
        row=c.execute("SELECT name FROM people WHERE event_id=? AND id!=? LIMIT 1",(eid,pid)).fetchone()
    assert breakdown["total_cents"]==budget
    assert breakdown["allocated_cents"]==budget
    assert breakdown["participant_count"]==count
    assert breakdown["split_method"]=="equal"
    assert breakdown["allocation_consistent"] is True
    assert breakdown["share_cents"]==private["share_cents"]
    assert sum(x["total_cents"] for x in breakdown["categories"])==budget
    assert all(set(x)=={"category","total_cents"} for x in breakdown["categories"])
    assert row["name"] not in str(private)
    assert "paypal_order_id" not in str(private)
    assert "idempotency" not in str(private)
    assert private["payment_mode"]=="NONE"
    assert private["identity_verified"] is False


def test_exact_cents_rounding_and_weighted_split_use_shared_allocator(client):
    import app
    eid,pid,auth=invitation(client)
    # Weighted allocation must recalculate and revoke old private links.
    with app.db() as c:
        c.execute("UPDATE people SET weight=2 WHERE id=?",(pid,))
        app.recalculate(c,eid,"weighted")
    assert client.get("/api/participant/overview",headers=auth).status_code==404
    refreshed=client.post(f"/api/events/{eid}/people/{pid}/invite").json()["token"]
    auth={"Authorization":"Bearer "+refreshed}
    d=overview(client,auth)
    assert d["share_breakdown"]["split_method"]=="weighted"
    assert d["share_breakdown"]["allocation_consistent"] is True
    with app.db() as c:
        members=[dict(x) for x in c.execute(
            "SELECT id,weight,share_cents FROM people WHERE event_id=?",(eid,)
        )]
        total=d["share_breakdown"]["total_cents"]
    from domain import allocate
    expected=allocate(total,members,"weighted")
    assert d["share_cents"]==expected[pid]
    assert sum(expected.values())==total


def test_stale_browser_quote_cannot_approve_or_write_history(client):
    eid,pid,auth=invitation(client)
    d=overview(client,auth)
    quote={"expected_share_cents":d["share_cents"],
           "expected_total_cents":d["share_breakdown"]["total_cents"]}
    for bad in [
        {"expected_share_cents":quote["expected_share_cents"]+1,
         "expected_total_cents":quote["expected_total_cents"]},
        {"expected_share_cents":quote["expected_share_cents"],
         "expected_total_cents":quote["expected_total_cents"]+1},
    ]:
        result=client.post("/api/participant/approve",headers=auth,json=bad)
        assert result.status_code==409,result.text
        assert "reviewed share or budget changed" in result.json()["detail"]
    assert overview(client,auth)["approved"] is False
    good=client.post("/api/participant/approve",headers=auth,json=quote)
    assert good.status_code==200,good.text
    assert overview(client,auth)["approved"] is True
    history=client.get(f"/api/events/{eid}/history").json()["entries"]
    assert sum(x["action"]=="participant_approved" for x in history)==1
    assert client.get("/api/state").json()["events"][0]["sandbox_cents"]==0


def test_corrupt_local_allocation_blocks_any_approval_even_legacy_clients(client):
    import app
    eid,pid,auth=invitation(client)
    correct=overview(client,auth)
    with app.db() as c:
        other=c.execute("SELECT id FROM people WHERE event_id=? AND id!=? LIMIT 1",
                        (eid,pid)).fetchone()
        c.execute("UPDATE people SET share_cents=share_cents+3 WHERE id=?",
                  (other["id"],))
    # This does not change the invited person's share, so the invitation
    # still resolves. The allocation consistency guard must reject consent.
    preview=overview(client,auth)
    assert preview["share_breakdown"]["allocation_consistent"] is False
    quote={"expected_share_cents":correct["share_cents"],
           "expected_total_cents":correct["share_breakdown"]["total_cents"]}
    for body in [quote,None]:
        result=client.post("/api/participant/approve",headers=auth,
                           **({"json":body} if body is not None else {}))
        assert result.status_code==409,result.text
        assert "allocation is inconsistent" in result.json()["detail"]
    assert overview(client,auth)["approved"] is False


def test_invalid_quote_schema_and_unauthorized_private_overview(client,monkeypatch):
    eid,pid,auth=invitation(client)
    response=client.post("/api/participant/approve",headers=auth,json={
        "expected_share_cents":"1100","expected_total_cents":2200})
    assert response.status_code==422
    response=client.post("/api/participant/approve",headers=auth,json={
        "expected_share_cents":1100,"expected_total_cents":2200,
        "payment_approval":True})
    assert response.status_code==422
    assert client.get("/api/participant/overview").status_code==401
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","a-secure-organizer-demo-password")
    assert client.get("/api/participant/overview").status_code==401
    valid=client.get("/api/participant/overview",headers=auth)
    assert valid.status_code==200
    assert "no-store" in valid.headers["Cache-Control"]
    assert client.get("/api/participant/overview",headers={
        **auth,"Origin":"https://untrusted.example","Sec-Fetch-Site":"cross-site"
    }).status_code==200  # Cross-origin block applies to *mutations*.
    assert client.post("/api/participant/approve",headers={
        **auth,"Origin":"https://untrusted.example","Sec-Fetch-Site":"cross-site"
    },json={"expected_share_cents":1100,"expected_total_cents":2200}).status_code==403
