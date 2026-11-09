"""PayPal REST API adapter: strictly sandbox, server-side credentials only."""
import os
import re
import uuid
from urllib.parse import urlparse, urlsplit
import httpx
from fastapi import HTTPException

BASE = "https://api-m.sandbox.paypal.com"
_ORDER_ID = re.compile(r"[A-Za-z0-9-]{5,50}\Z")
MAX_SANDBOX_ORDER_CENTS = (2**53 - 1) // 10
_USD_AMOUNT = re.compile(r"(?:0|[1-9][0-9]{0,12})(?:\.[0-9]{1,2})?\Z")


def valid_sandbox_order_id(value):
    """Allow only safe ASCII identifiers for both storage and provider GETs."""
    return isinstance(value, str) and bool(_ORDER_ID.fullmatch(value))


def _clean_https_url(url):
    """Reject control, whitespace and overlong URLs before urllib normalization."""
    return (isinstance(url, str) and 1 <= len(url) <= 2048
            and url.isascii() and not any(char.isspace() or ord(char) < 32
                                           or ord(char) == 127 for char in url))


def trusted_sandbox_checkout_url(url):
    """Only clean HTTPS URLs on an exact PayPal Sandbox host and safe port."""
    if not _clean_https_url(url):
        return False
    try:
        parsed = urlparse(url)
        return (parsed.scheme == "https"
                and parsed.hostname in ("www.sandbox.paypal.com", "sandbox.paypal.com")
                and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443)
                and not parsed.fragment
                and parsed.path.startswith("/"))
    except ValueError:
        return False


def trusted_checkout_return_url(url):
    """Only the protected workspace return target, never an arbitrary URI.

    Local HTTP is intentionally allowed *only* on loopback and when not
    running in hosted mode. Any HTTPS origin can host a self-deployed
    instance; the app builds this URL from its configured public base.
    """
    if not _clean_https_url(url):
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.username is None and parsed.password is None
            and parsed.hostname is not None
            and parsed.port not in (0,)
            and not parsed.fragment
            and parsed.path == "/workspace"
            and parsed.query == "payment=return"
            and (parsed.scheme == "https" or (
                parsed.scheme == "http"
                and os.getenv("CIRCLESPLIT_HOSTED") != "1"
                and parsed.hostname in ("localhost", "127.0.0.1")
            ))
        )
    except ValueError:
        return False


def configured():
    return bool(os.getenv("PAYPAL_CLIENT_ID") and os.getenv("PAYPAL_CLIENT_SECRET"))

def parse_usd_cents(value):
    """Parse provider USD values without floats or decimal coercion.

    PayPal Orders v2 and webhook amount.value are strings in the JSON API.
    Reject exponents, extra fractional digits, whitespace, Unicode digits,
    malformed types and out-of-range values. This does not prove settlement.
    """
    if not isinstance(value, str) or not _USD_AMOUNT.fullmatch(value):
        return None
    dollars, _, fraction = value.partition(".")
    cents = int(dollars) * 100 + int((fraction + "00")[:2])
    return cents if cents <= MAX_SANDBOX_ORDER_CENTS else None


def same_amount(value, amount_cents):
    return (type(amount_cents) is int
            and 0 <= amount_cents <= MAX_SANDBOX_ORDER_CENTS
            and parse_usd_cents(value) == amount_cents)

async def token():
    if not configured():
        raise HTTPException(503, "PayPal sandbox credentials not configured")
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(BASE + "/v1/oauth2/token",
                auth=(os.environ["PAYPAL_CLIENT_ID"], os.environ["PAYPAL_CLIENT_SECRET"]),
                data={"grant_type": "client_credentials"})
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise ValueError("Invalid provider OAuth response shape")
            access_token = payload.get("access_token")
            if (not isinstance(access_token, str)
                    or not 1 <= len(access_token) <= 4096
                    or not access_token.isascii()
                    or any(char.isspace() or ord(char) < 33 or ord(char) == 127
                           for char in access_token)):
                raise ValueError("Invalid provider OAuth token")
            return access_token
    except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError):
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
            result = response.json()
            if not isinstance(result, dict):
                raise ValueError("Invalid provider JSON envelope")
            return result
    except httpx.HTTPStatusError as error:
        raise HTTPException(502, "PayPal sandbox HTTP " + str(error.response.status_code))
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        # Upstream POST requests are potentially ambiguous; callers keep
        # the original local payment attempt locked pending manual review.
        raise HTTPException(502, "PayPal sandbox request failed")

async def order(amount, event_id, person_id, return_url, request_id):
    # The checkout amount comes from server-side, exact-cent allocation.
    # Guard the adapter boundary too: never coerce floats, bools or invalid
    # magnitudes and never send an upstream Sandbox request for bad cents.
    if type(amount) is not int or not 1 <= amount <= MAX_SANDBOX_ORDER_CENTS:
        raise HTTPException(400, "Sandbox order amount must be positive safe integer cents")
    if not trusted_checkout_return_url(return_url):
        raise HTTPException(400, "A trusted HTTPS workspace return URL is required")
    body = {
        "intent": "CAPTURE",
        "purchase_units": [{"reference_id": str(event_id) + "-" + str(person_id),
            "custom_id": str(event_id) + ":" + str(person_id),
            "description": "CircleSplit test contribution",
            "amount": {"currency_code": "USD", "value": f"{amount // 100}.{amount % 100:02d}"}}],
        "payment_source": {"paypal": {"experience_context": {
            "user_action": "PAY_NOW", "shipping_preference": "NO_SHIPPING",
            "return_url": return_url,
            "cancel_url": return_url.split("?")[0] + "?payment=cancelled"}}}
    }
    response = await api("POST", "/v2/checkout/orders", body, request_id)
    # Never redirect the organizer to an arbitrary URL supplied by a provider
    # payload or a compromised/misconfigured intermediary.
    url = approval_link(response)
    if not isinstance(response, dict) or not valid_sandbox_order_id(response.get("id")) or not url:
        raise HTTPException(502, "PayPal did not return a valid order ID and trusted sandbox approval link")
    return {"id": response["id"], "approval_url": url}

async def capture(order_id, idempotency_key):
    if not valid_sandbox_order_id(order_id):
        raise HTTPException(400, "Invalid sandbox order ID")
    return await api("POST", "/v2/checkout/orders/" + order_id + "/capture", {}, idempotency_key)

async def details(order_id):
    # Order IDs are looked up in our database before calling this function.
    # Revalidate at the network adapter boundary to reject future unsafe callers.
    if not valid_sandbox_order_id(order_id):
        raise HTTPException(400, "Invalid sandbox order ID")
    return await api("GET", "/v2/checkout/orders/" + order_id)

def approval_link(details):
    # A malformed signed-looking provider payload must never produce a 500
    # or redirect to arbitrary host, scheme, script, or credentials.
    if not isinstance(details, dict):
        return None
    links = details.get("links")
    if not isinstance(links, list) or len(links) > 50:
        return None
    for entry in links:
        if not isinstance(entry, dict) or entry.get("rel") not in ("payer-action", "approve"):
            continue
        url = entry.get("href")
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

def _valid_sandbox_webhook_headers(fields):
    """Validate public webhook headers before any OAuth/provider request.

    Header lengths follow PayPal's verification API schema. The certificate
    URL must point to a PayPal Sandbox webhook certificate, not an arbitrary
    URL supplied by a public caller. PayPal still authenticates the actual
    signature via verify-webhook-signature; shape checks are not verification.
    """
    if not isinstance(fields, dict):
        return False
    auth_algo = fields.get("auth_algo")
    transmission_id = fields.get("transmission_id")
    transmission_time = fields.get("transmission_time")
    transmission_sig = fields.get("transmission_sig")
    cert_url = fields.get("cert_url")
    limits = {
        "auth_algo": 100, "transmission_id": 50,
        "transmission_time": 100, "transmission_sig": 500,
        "cert_url": 500,
    }
    for name, maximum in limits.items():
        value = fields.get(name)
        if (not isinstance(value, str) or not 1 <= len(value) <= maximum
                or not value.isascii() or
                any(ord(ch) <= 32 or ord(ch) == 127 for ch in value)):
            return False
    if not re.fullmatch(r"[A-Za-z0-9]+", auth_algo):
        return False
    if not re.fullmatch(r"[A-Za-z0-9._-]+", transmission_id):
        return False
    if not re.fullmatch(r"[0-9TtZz:+.-]+", transmission_time):
        return False
    if not re.fullmatch(r"[A-Za-z0-9+/=_-]+", transmission_sig):
        return False
    if not _clean_https_url(cert_url):
        return False
    try:
        parsed = urlsplit(cert_url)
        return (parsed.scheme == "https"
                and parsed.hostname in (
                    "api-m.sandbox.paypal.com", "api.sandbox.paypal.com")
                and parsed.username is None and parsed.password is None
                and parsed.port in (None, 443)
                and not parsed.query and not parsed.fragment
                and re.fullmatch(
                    r"/v1/notifications/certs/CERT-[A-Za-z0-9-]{8,128}",
                    parsed.path) is not None)
    except ValueError:
        return False


async def verify_webhook(headers, event):
    webhook_id = os.getenv("PAYPAL_WEBHOOK_ID")
    if not webhook_id:
        raise HTTPException(503, "Sandbox webhook verification unconfigured")
    mapping = {"auth_algo": "paypal-auth-algo", "cert_url": "paypal-cert-url",
               "transmission_id": "paypal-transmission-id",
               "transmission_sig": "paypal-transmission-sig",
               "transmission_time": "paypal-transmission-time"}
    fields = {name: headers.get(header, "") for name, header in mapping.items()}
    if not _valid_sandbox_webhook_headers(fields):
        raise HTTPException(400, "Invalid PayPal Sandbox webhook signature headers")
    response = await api("POST", "/v1/notifications/verify-webhook-signature",
                         {"webhook_id": webhook_id, "webhook_event": event, **fields},
                         str(uuid.uuid4()))
    if not isinstance(response, dict) or response.get("verification_status") != "SUCCESS":
        # A malformed/unknown provider verification result is not approval.
        # Never settle or acknowledge a capture unless the provider explicitly
        # confirmed a valid signature.
        raise HTTPException(401, "Invalid webhook signature")
    return True
