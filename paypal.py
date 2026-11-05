"""PayPal REST API adapter: strictly sandbox, server-side credentials only."""
import os
import re
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException

BASE = "https://api-m.sandbox.paypal.com"
_ORDER_ID = re.compile(r"[A-Za-z0-9-]{5,50}\\Z")


def valid_sandbox_order_id(value):
    """Allow only safe ASCII identifiers for both storage and provider GETs."""
    return isinstance(value, str) and bool(_ORDER_ID.fullmatch(value))


def trusted_sandbox_checkout_url(url):
    """Only HTTPS links to PayPal Sandbox, with no credentials or alternate port."""
    if not isinstance(url, str):
        return False
    try:
        parsed = urlparse(url)
        return (parsed.scheme == "https"
                and parsed.hostname in ("www.sandbox.paypal.com", "sandbox.paypal.com")
                and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443))
    except ValueError:
        return False


def configured():
    return bool(os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_CLIENT_SECRET"))

def same_amount(value, amount_cents):
    try:
        number = Decimal(str(value))
        return number.is_finite() and number * 100 == amount_cents
    except (ValueError, TypeError, InvalidOperation):
        return False

async def token():
    if not configured():
        raise HTTPException(503, "PayPal sandbox credentials not configured")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(BASE + "/v1/oauth2/token",
                auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"]),
                data={"grant_type": "client_credentials"})
            response.raise_for_status()
            return response.json()["access_token"]
    except (httpx.HTTPError, KeyError, ValueError):
        raise HTTPException(502, "PayPal sandbox authentication failed")

async def api(method, path, data=None, request_id=None):
    headers = {"Authorization": "Bearer " + await token(),
               "Content-Type": "application/json"}
    if request_id:
        headers["PayPal-Request-Id"] = request_id
    try:
        async with httpx.AsyncClient(timeout=25) as client:
            response = await client.request(method, BASE + path, headers=headers, json=data)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as error:
        raise HTTPException(502, "PayPal sandbox HTTP " + str(error.response.status_code))
    except (httpx.HTTPError, ValueError):
        raise HTTPException(502, "PayPal sandbox request failed")

async def order(amount, event_id, person_id, return_url, request_id):
    parsed = urlparse(return_url)
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1"):
        raise HTTPException(400, "HTTPS public return URL required")
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{"reference_id": str(event_id) + "-" + str(person_id),
            "custom_id": str(event_id) + ":" + str(person_id),
            "description": "CircleSplit test contribution",
            "amount": {"currency_code": "USD", "value": f"{amount / 100:.2f}"}}],
        "payment_source": {"paypal": {"experience_context": {
            "user_action": "PAY_NOW", "shipping_preference": "NO_SHIPPING",
            "return_url": return_url,
            "cancel_url": return_url.split("?")[0] + "?payment=cancelled"}}}
    }
    response = await api("POST", "/v2/checkout/orders", body, request_id)
    # Never redirect the organizer to an arbitrary URL supplied by a provider
    # payload or a compromised/misconfigured intermediary.
    url = approval_link(response)
    if not valid_sandbox_order_id(response.get("id")) or not url:
        raise HTTPException(502, "PayPal did not return a valid order ID and trusted sandbox approval link")
    return {"id": response["id"], "approval_url": url}

async def capture(order_id, idempotency_key):
    return await api("POST", "/v2/checkout/orders/" + order_id + "/capture", {}, idempotency_key)

async def details(order_id):
    # Order IDs are looked up in our database before calling this function.
    return await api("GET", "/v2/checkout/orders/" + order_id)

def approval_link(details):
    # Never redirect to an arbitrary URL taken from remote JSON.
    for entry in details.get("links", []):
        if entry.get("rel") not in ("payer-action", "approve"):
            continue
        url = entry.get("href")
        if not isinstance(url, str):
            continue
        parsed = urlparse(url)
        if trusted_sandbox_checkout_url(url):
            return url
    return None

def completed_capture(response, amount):
    """Accept only a single, unambiguous completed capture for one purchase unit.

    A matching capture must not hide an additional capture, extra purchase unit,
    or malformed provider payload. Such responses require manual review rather
    than recording an arbitrary transaction as settled.
    """
    if not isinstance(response, dict):
        return None
    units = response.get("purchase_units")
    if not isinstance(units, list) or len(units) != 1:
        return None
    unit = units[0]
    if not isinstance(unit, dict):
        return None
    payments = unit.get("payments")
    if not isinstance(payments, dict):
        return None
    captures = payments.get("captures")
    if not isinstance(captures, list) or len(captures) != 1:
        return None
    capture = captures[0]
    if not isinstance(capture, dict) or not isinstance(capture.get("amount"), dict):
        return None
    identifier = capture.get("id")
    if (not isinstance(identifier, str)
            or not 1 <= len(identifier) <= 128
            or not identifier.isascii()
            or not all(c.isalnum() or c == "-" for c in identifier)):
        return None
    if (capture.get("status") != "COMPLETED"
            or capture["amount"].get("currency_code") != "USD"
            or not same_amount(capture["amount"].get("value"), amount)):
        return None
    return capture

async def verify_webhook(headers, event):
    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID")
    if not webhook_id:
        raise HTTPException(503, "Sandbox webhook verification unconfigured")
    mapping = {"auth_algo": "paypal-auth-algo", "cert_url": "paypal-cert-url",
               "transmission_id": "paypal-transmission-id",
               "transmission_sig": "paypal-transmission-sig",
               "transmission_time": "paypal-transmission-time"}
    fields = {name: headers.get(header, "") for name, header in mapping.items()}
    if any(not v for v in fields.values()):
        raise HTTPException(400, "Missing signature verification headers")
    response = await api("POST", "/v1/notifications/verify-webhook-signature",
                         {"webhook_id": webhook_id, "webhook_event": event, **fields},
                         str(uuid.uuid4()))
    if response.get("verification_status") != "SUCCESS":
        raise HTTPException(401, "Invalid webhook signature")
    return True
