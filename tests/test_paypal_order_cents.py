"""PayPal Sandbox request-contract tests. Every upstream request is mocked.

The real adapter must never send malformed money to an external provider,
and valid integer-cent amounts must not be converted through binary floats.
"""
import asyncio
from decimal import Decimal

import pytest
from fastapi import HTTPException

import paypal


RETURN_URL = "https://circlesplit-ai-demo.onrender.com/workspace?payment=return"
FAKE_APPROVAL = "https://www.sandbox.paypal.com/checkoutnow?token=MOCKORDER-12345"


def fake_provider_calls(monkeypatch):
    calls = []

    async def pretend_api(method, path, data=None, request_id=None):
        calls.append((method, path, data, request_id))
        return {
            "id": "MOCKORDER-12345",
            "links": [{"rel": "payer-action", "href": FAKE_APPROVAL}],
        }

    monkeypatch.setattr(paypal, "api", pretend_api)
    return calls


@pytest.mark.parametrize(("cents", "expected"), [
    (1, "0.01"),
    (9, "0.09"),
    (10, "0.10"),
    (101, "1.01"),
    (1005, "10.05"),
    (9999999, "99999.99"),
    (2000000000, "20000000.00"),
    ((2**53 - 1) // 10, "9007199254740.99"),
])
def test_valid_sandbox_orders_use_exact_decimal_cent_strings_without_real_provider(
    monkeypatch, cents, expected
):
    calls = fake_provider_calls(monkeypatch)
    order = asyncio.run(paypal.order(cents, 15, 7, RETURN_URL, "test-request-1"))
    assert order == {"id": "MOCKORDER-12345", "approval_url": FAKE_APPROVAL}
    assert len(calls) == 1
    method, path, body, key = calls[0]
    assert method == "POST"
    assert path == "/v2/checkout/orders"
    assert key == "test-request-1"
    amount = body["purchase_units"][0]["amount"]
    assert amount == {"currency_code": "USD", "value": expected}
    assert body["purchase_units"][0]["custom_id"] == "15:7"


@pytest.mark.parametrize("bad_cents", [
    None, False, True, 0, -1, 1.0, 1.01, "1", "1.00",
    Decimal("100"), float("nan"), float("inf"), (2**53 - 1) // 10 + 1,
])
def test_invalid_sandbox_cents_fail_before_any_provider_call(monkeypatch, bad_cents):
    calls = fake_provider_calls(monkeypatch)
    with pytest.raises(HTTPException) as err:
        asyncio.run(paypal.order(bad_cents, 15, 7, RETURN_URL, "test-request-2"))
    assert err.value.status_code == 400
    assert "integer cents" in err.value.detail
    assert calls == []


def test_untrusted_callback_still_blocks_provider_before_order_creation(monkeypatch):
    calls = fake_provider_calls(monkeypatch)
    with pytest.raises(HTTPException) as err:
        asyncio.run(paypal.order(
            101, 15, 7, "https://attacker.example/workspace?payment=return#fragment",
            "test-request-3"
        ))
    assert err.value.status_code == 400
    assert calls == []
