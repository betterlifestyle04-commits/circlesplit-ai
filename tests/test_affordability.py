"""Read-only affordability planning must never mutate a funded event."""
import importlib

import pytest
from fastapi.testclient import TestClient
from domain import allocate
import paypal


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("CIRCLESPLIT_DB", str(tmp_path / "affordability.sqlite3"))
    monkeypatch.delenv("CIRCLESPLIT_HOSTED", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_ID", raising=False)
    monkeypatch.delenv("PAYPAL_CLIENT_SECRET", raising=False)
    import app
    importlib.reload(app)
    with TestClient(app.app) as instance:
        yield instance


def default_event(client):
    return client.get("/api/state").json()["events"][0]


def preview(client, eid, cap, max_extra=50, strategy="equal"):
    return client.post(
        f"/api/events/{eid}/affordability",
        json={
            "max_share": cap,
            "maximum_extra_people": max_extra,
            "strategy": strategy,
        },
    )


def test_existing_twenty_people_need_exactly_two_more_for_ten_dollar_cap(client):
    event = default_event(client)
    before = client.get("/api/state").json()
    response = preview(client,event["id"],"10.00")
    assert response.status_code==200,response.text
    data=response.json()
    assert data["mode"]=="SANDBOX_PLANNING_ONLY"
    assert data["read_only"] is True
    assert data["cap_cents"]==1000
    assert data["budget_cents"]==22000
    assert data["current_people"]==20
    assert data["current_largest_share_cents"]==1100
    assert data["feasible"] is True
    assert data["minimum_additional_people"]==2
    assert data["recommendation"]=={
        "additional_people":2,
        "total_people":22,
        "largest_share_cents":1000,
        "smallest_share_cents":1000
    }
    assert data["remaining_largest_share_gap_cents"]==0
    assert data["candidates_tested"]==3
    assert client.get("/api/state").json()==before


def test_current_plan_already_below_cap_recommends_zero_more(client):
    event=default_event(client)
    result=preview(client,event["id"],"11.00",50).json()
    assert result["feasible"] is True
    assert result["minimum_additional_people"]==0
    assert result["candidates_tested"]==1
    assert result["recommendation"]["largest_share_cents"]==1100


def test_unreachable_cap_reports_best_case_without_claiming_success(client):
    event=default_event(client)
    data=preview(client,event["id"],"10.00",1).json()
    assert data["feasible"] is False
    assert data["minimum_additional_people"] is None
    assert data["recommendation"]["additional_people"]==1
    assert data["recommendation"]["largest_share_cents"]==1048
    assert data["remaining_largest_share_gap_cents"]==48
    assert data["requested_maximum_extra_people"]==1
    assert data["tested_maximum_extra_people"]==1


def test_solver_is_bounded_and_can_report_infeasibility(client):
    event=default_event(client)
    data=preview(client,event["id"],"0.01",50).json()
    assert data["feasible"] is False
    assert data["candidates_tested"]==51
    assert data["recommendation"]["additional_people"]==50
    assert data["recommendation"]["largest_share_cents"]>1
    assert data["remaining_largest_share_gap_cents"]>0


def test_weighted_solver_uses_actual_integer_cent_allocator(client):
    created=client.post("/api/events",json={
        "name":"Weighted activity","date":"2026-11-12"
    }).json()
    eid=created["id"]
    assert client.post(f"/api/events/{eid}/expenses",
        json={"title":"Venue","amount":"100.00"}).status_code==200
    for name,weight in (("Person A",3),("Person B",1)):
        result=client.post(f"/api/events/{eid}/people",
            json={"name":name,"weight":weight})
        assert result.status_code==200,result.text
    response=preview(client,eid,"50.00",5,"weighted")
    assert response.status_code==200,response.text
    data=response.json()
    assert data["strategy"]=="weighted"
    assert data["current_largest_share_cents"]==7500
    assert data["feasible"] is True
    assert data["minimum_additional_people"]==2
    assert data["recommendation"]["largest_share_cents"]==5000
    assert data["recommendation"]["total_people"]==4
    assert data["recommendation"]["smallest_share_cents"]==1666
    assert data["budget_cents"]==10000


def test_empty_event_requires_one_fictional_attendee_but_no_costs(client):
    event=client.post("/api/events",json={
        "name":"Empty new event","date":"2026-11-12"
    }).json()
    eid=event["id"]
    assert preview(client,eid,"10.00",0).status_code==422
    data=preview(client,eid,"10.00",2).json()
    assert data["feasible"] is True
    assert data["current_people"]==0
    assert data["current_largest_share_cents"] is None
    assert data["minimum_additional_people"]==1
    assert data["recommendation"]["largest_share_cents"]==0


@pytest.mark.parametrize("payload",[
    {"max_share":"0"},
    {"max_share":"0.00"},
    {"max_share":"-10.00"},
    {"max_share":"1.234"},
    {"max_share":"NaN"},
    {"max_share":"Infinity"},
    {"max_share":"1e2"},
    {"max_share":"100000.01"},
    {"max_share":"10."},
    {"max_share":10.0},
    {"max_share":True},
    {"max_share":"$10.00"},
    {"max_share":"10.00","maximum_extra_people":-1},
    {"max_share":"10.00","maximum_extra_people":51},
    {"max_share":"10.00","maximum_extra_people":1.5},
    {"max_share":"10.00","maximum_extra_people":"5"},
    {"max_share":"10.00","maximum_extra_people":True},
    {"max_share":"10.00","maximum_extra_people":5,"strategy":"arbitrary"},
    {"max_share":"10.00","maximum_extra_people":5,"do_payment":True},
])
def test_invalid_or_dangerous_inputs_fail_closed(client,payload):
    event=default_event(client)
    body={"max_share":"10.00","maximum_extra_people":50,"strategy":"equal"}
    body.update(payload)
    response=client.post(f"/api/events/{event['id']}/affordability",json=body)
    assert response.status_code==422,response.text


def test_read_only_after_approval_and_simulated_payment(client):
    event=default_event(client)
    eid=event["id"]
    pid=event["people"][0]["id"]
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    assert client.post(f"/api/events/{eid}/people/{pid}/simulate").status_code==200
    import app
    with app.db() as c:
        count_before=c.execute("SELECT COUNT(*) FROM event_history").fetchone()[0]
        payments_before=c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]
    before=client.get("/api/state").json()
    response=preview(client,eid,"9.00",50,"equal")
    assert response.status_code==200,response.text
    data=response.json()
    assert data["paid_or_simulated_people"]>=1
    assert data["has_existing_sandbox_orders"] is False
    assert data["read_only"] is True
    assert client.get("/api/state").json()==before
    with app.db() as c:
        assert c.execute("SELECT COUNT(*) FROM event_history").fetchone()[0]==count_before
        assert c.execute("SELECT COUNT(*) FROM payments").fetchone()[0]==payments_before


def test_existing_sandbox_order_does_not_allow_mutation_or_new_order(client,monkeypatch):
    event=default_event(client)
    eid=event["id"]
    pid=event["people"][0]["id"]
    import app
    assert client.post(f"/api/events/{eid}/people/{pid}/approve").status_code==200
    monkeypatch.setattr(paypal,"configured",lambda:True)
    calls=[]
    async def order(*args,**kwargs):
        calls.append(args)
        return {"id":"AFFORDABILITY-ORDER-1",
                "approval_url":"https://www.sandbox.paypal.com/checkoutnow?token=TEST"}
    monkeypatch.setattr(paypal,"order",order)
    assert client.post(f"/api/paypal/orders/{eid}/{pid}").status_code==200
    before=client.get("/api/state").json()
    response=preview(client,eid,"9.00",10)
    assert response.status_code==200,response.text
    assert response.json()["has_existing_sandbox_orders"] is True
    assert response.json()["approved_people"]>=1
    assert client.get("/api/state").json()==before
    assert len(calls)==1
    with app.db() as c:
        assert c.execute("SELECT COUNT(*) FROM payments WHERE event_id=?",(eid,)).fetchone()[0]==1


def test_only_existing_event_and_authorized_organizer_can_preview(client,monkeypatch):
    assert preview(client,999999,"10.00",1).status_code==404
    event=default_event(client)
    eid=event["id"]
    monkeypatch.setenv("CIRCLESPLIT_HOSTED","1")
    monkeypatch.setenv("DEMO_PASSWORD","long-private-shared-judge-password")
    assert preview(client,eid,"10.00").status_code==401
    response=client.post(f"/api/events/{eid}/affordability",
        json={"max_share":"10.00","maximum_extra_people":10},
        auth=("judge","long-private-shared-judge-password"))
    assert response.status_code==200,response.text
    assert response.headers.get("Cache-Control")=="no-store"
    assert "PRIVATE-ORDER" not in response.text
