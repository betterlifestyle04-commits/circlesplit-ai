"""Fail-closed validation of external webhook signature headers.

No live PayPal requests or credentials: postback verification is stubbed.
The header shape preflight is not an alternative to signature verification.
"""
import asyncio

from fastapi import HTTPException
import pytest

import paypal


VALID = {
    "paypal-auth-algo": "SHA256withRSA",
    "paypal-cert-url": (
        "https://api.sandbox.paypal.com/v1/notifications/certs/"
        "CERT-360caa42-fca2a594-ab66f33d"
    ),
    "paypal-transmission-id": "db49fb10-1343-11ef-ac58-e32457403f67",
    "paypal-transmission-sig": "Zk9vL3M0bWQxZzM0Nw==",
    "paypal-transmission-time": "2026-11-09T19:30:17.223Z",
}
EVENT = {"id": "WH-FICTIONAL-001", "event_type": "PAYMENT.CAPTURE.COMPLETED"}


def provider_stub(monkeypatch, response=None):
    calls = []
    async def fake_api(method, path, data=None, request_id=None):
        calls.append((method, path, data, request_id))
        return response if response is not None else {"verification_status": "SUCCESS"}
    monkeypatch.setenv("PAYPAL_WEBHOOK_ID", "WH-FICTIONAL-CONFIGURED-ID")
    monkeypatch.setattr(paypal, "api", fake_api)
    return calls


def verify(headers):
    return asyncio.run(paypal.verify_webhook(headers, EVENT))


def test_valid_paypal_sandbox_headers_require_real_postback_verification(monkeypatch):
    calls = provider_stub(monkeypatch)
    assert verify(VALID) is True
    assert len(calls) == 1
    method, path, data, request_id = calls[0]
    assert method == "POST" and path == "/v1/notifications/verify-webhook-signature"
    assert data["cert_url"] == VALID["paypal-cert-url"]
    assert data["webhook_id"] == "WH-FICTIONAL-CONFIGURED-ID"
    assert data["webhook_event"] == EVENT
    assert request_id

    # Both established PayPal Sandbox API hostnames are accepted.
    other = dict(VALID)
    other["paypal-cert-url"] = other["paypal-cert-url"].replace(
        "api.sandbox.paypal.com", "api-m.sandbox.paypal.com")
    assert verify(other) is True
    assert len(calls) == 2


@pytest.mark.parametrize(("header", "invalid"), [
    ("paypal-auth-algo", ""),
    ("paypal-auth-algo", "SHA256withRSA;unsafe"),
    ("paypal-auth-algo", "A" * 101),
    ("paypal-transmission-id", "A" * 51),
    ("paypal-transmission-id", "x\nFake: injected"),
    ("paypal-transmission-sig", "@" * 20),
    ("paypal-transmission-sig", "A" * 501),
    ("paypal-transmission-time", "2026-11-09T19:30:17Z\r\nInjected: 1"),
    ("paypal-transmission-time", "A" * 101),
    ("paypal-cert-url", "https://attacker.example/v1/notifications/certs/CERT-360caa42-fca2a594-ab66f33d"),
    ("paypal-cert-url", "http://api.sandbox.paypal.com/v1/notifications/certs/CERT-360caa42-fca2a594-ab66f33d"),
    ("paypal-cert-url", "https://api.sandbox.paypal.com.evil.example/v1/notifications/certs/CERT-360caa42-fca2a594-ab66f33d"),
    ("paypal-cert-url", "https://user@api.sandbox.paypal.com/v1/notifications/certs/CERT-360caa42-fca2a594-ab66f33d"),
    ("paypal-cert-url", "https://api.sandbox.paypal.com:444/v1/notifications/certs/CERT-360caa42-fca2a594-ab66f33d"),
    ("paypal-cert-url", "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-360caa42-fca2a594-ab66f33d?target=evil"),
    ("paypal-cert-url", "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-360caa42-fca2a594-ab66f33d#fragment"),
    ("paypal-cert-url", "https://api.sandbox.paypal.com@evil.example/v1/notifications/certs/CERT-360caa42-fca2a594-ab66f33d"),
    ("paypal-cert-url", "https://api.sandbox.paypal.com/v1/notifications/other/CERT-360caa42-fca2a594-ab66f33d"),
    ("paypal-cert-url", "https://api.sandbox.paypal.com/v1/notifications/certs/CERT-1"),
    ("paypal-cert-url", "A" * 501),
])
def test_malformed_webhook_headers_make_zero_paypal_calls(monkeypatch, header, invalid):
    calls = provider_stub(monkeypatch)
    payload = dict(VALID, **{header: invalid})
    with pytest.raises(HTTPException) as err:
        verify(payload)
    assert err.value.status_code == 400
    assert calls == []


def test_missing_headers_and_unconfigured_webhook_never_call_provider(monkeypatch):
    calls = provider_stub(monkeypatch)
    for header in VALID:
        payload = dict(VALID)
        del payload[header]
        with pytest.raises(HTTPException) as err:
            verify(payload)
        assert err.value.status_code == 400
        assert calls == []
    monkeypatch.delenv("PAYPAL_WEBHOOK_ID")
    with pytest.raises(HTTPException) as err:
        verify(VALID)
    assert err.value.status_code == 503
    assert calls == []


def test_valid_shape_cannot_bypass_failed_paypal_signature_verification(monkeypatch):
    calls = provider_stub(monkeypatch, {"verification_status": "FAILURE"})
    with pytest.raises(HTTPException) as err:
        verify(VALID)
    assert err.value.status_code == 401
    assert len(calls) == 1


def test_malformed_provider_verification_reply_does_not_validate(monkeypatch):
    calls = provider_stub(monkeypatch, ["SUCCESS"])
    with pytest.raises(HTTPException) as err:
        verify(VALID)
    assert err.value.status_code == 401
    assert len(calls) == 1
