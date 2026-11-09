"""Exact-cent USD contract tests for the PayPal Sandbox provider adapter.

No external services are called. The string parser is shared by capture,
order-status reconciliation and the verified-webhook amount checks.
"""
from decimal import Decimal

import pytest

import paypal


@pytest.mark.parametrize(("amount", "cents"), [
    ("0", 0), ("0.0", 0), ("0.00", 0), ("0.01", 1),
    ("0.1", 10), ("1", 100), ("1.2", 120), ("1.23", 123),
    ("11.00", 1100), ("99999.99", 9999999),
    ("9007199254740.99", paypal.MAX_SANDBOX_ORDER_CENTS),
])
def test_valid_usd_provider_strings_convert_to_exact_cents(amount, cents):
    assert paypal.parse_usd_cents(amount) == cents
    assert paypal.same_amount(amount, cents)
    assert not paypal.same_amount(amount, cents + 1)


@pytest.mark.parametrize("amount", [
    None, True, False, 1, 1.0, Decimal("1.00"), [], {},
    "", " ", " 1.00", "1.00 ", "1\n.00", "\t1.00",
    "+1.00", "-1.00", ".99", "1.", "1.234",
    "1e0", "1E+0", "1e-2", "NaN", "Inf", "Infinity",
    "01", "00.01", "000", "1,000.00", "$1.00",
    "１.００", "١.٠٠", "0x10", "1_000", "1 USD",
    "9007199254741.00", "99999999999999.99",
])
def test_invalid_usd_provider_strings_cannot_match_even_if_numerically_equivalent(amount):
    assert paypal.parse_usd_cents(amount) is None
    assert not paypal.same_amount(amount, 100)
    assert not paypal.same_amount(amount, 1)


@pytest.mark.parametrize("bad_expected", [None, True, False, 1.0, Decimal("1"), "100", -1,
                                       paypal.MAX_SANDBOX_ORDER_CENTS + 1])
def test_expected_cents_must_be_safe_nonnegative_integer(bad_expected):
    assert not paypal.same_amount("1.00", bad_expected)


@pytest.mark.parametrize("bad_value", ["1e1", "10.000", 10, 10.0, "010.00", "10.00\n"])
def test_completed_sandbox_capture_must_match_canonical_provider_amount(bad_value):
    response = {"purchase_units": [{
        "payments": {"captures": [{
            "id": "CAPTURE-CANONICAL-123",
            "status": "COMPLETED",
            "amount": {"currency_code": "USD", "value": bad_value},
        }]}
    }]}
    assert paypal.completed_capture(response, 1000) is None
    response["purchase_units"][0]["payments"]["captures"][0]["amount"]["value"] = "10.00"
    verified = paypal.completed_capture(response, 1000)
    assert verified is not None
    assert verified["id"] == "CAPTURE-CANONICAL-123"


def test_cents_range_is_identical_for_order_creation_and_provider_verification():
    assert paypal.MAX_SANDBOX_ORDER_CENTS == (2**53 - 1) // 10
    assert paypal.parse_usd_cents("9007199254740.99") == paypal.MAX_SANDBOX_ORDER_CENTS
    assert paypal.parse_usd_cents("9007199254741.00") is None
