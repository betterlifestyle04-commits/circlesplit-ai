"""PayPal REST API adapter: strictly sandbox, server-side credentials only."""
import os
import uuid
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse
import httpx
from fastapi import HTTPException

BASE = "https://api-m.sandbox.paypal.com"

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
    url = next((a.get("href") for a in response.get("links", [])
                if a.get("rel") in ("payer-action", "approve")), None)
    if not response.get("id") or not url:
        raise HTTPException(502, "PayPal did not return an approval link")
    return {"id": response["id"], "approval_url": url}

async def capture(order_id, idempotency_key):
    return await api("POST", "/v2/checkout/orders/" + order_id + "/capture", {}, idempotency_key)

def completed_capture(response, amount):
    captures = [c for unit in response.get("purchase_units", [])
                for c in unit.get("payments", {}).get("captures", [])]
    return next((c for c in captures if c.get("status") == "COMPLETED"
                 and c.get("id") and c.get("amount", {}).get("currency_code") == "USD"
                 and same_amount(c.get("amount", {}).get("value"), amount)), None)

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
