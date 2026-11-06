"""Browser-origin checks and defensive response headers for the hosted demo.

These are defence in depth, not replacements for individual account identity,
CSRF tokens, a durable database or payment-provider verification.
"""
from urllib.parse import urlsplit


_UNSAFE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Browser-local public pages need these exact, audited executable assets.
# Everything else under /static/ (especially the organizer workspace)
# keeps the hosted Basic-auth boundary. No prefix matching or wildcards.
PUBLIC_DEMO_SCRIPT_PATHS = frozenset({
    "/static/public_recovery.js",
    "/static/public_portability.js",
    "/static/public_scenarios.js",
    "/static/judge_walkthrough.js",
})


def public_demo_script(method, path):
    return method in ("GET", "HEAD") and path in PUBLIC_DEMO_SCRIPT_PATHS



def owner_only_sandbox_action(method, path):
    """Judge credentials may inspect, but must NEVER initiate provider actions.

    Deliberately guards all non-webhook POST routes under /api/paypal/,
    including future PayPal mutating routes, rather than enumerating just
    the current create/capture endpoints. Signature-verified webhooks must
    remain accessible without an organizer password.
    """
    return (method == "POST" and isinstance(path, str)
            and path.startswith("/api/paypal/")
            and path != "/api/paypal/webhook")


def _parsed_origin(value):
    """Normalize a web origin while rejecting malformed or non-origin strings."""
    if not isinstance(value, str) or not value or value != value.strip():
        return None
    try:
        parsed = urlsplit(value)
        if (parsed.scheme.lower() not in ("http", "https")
                or not parsed.hostname or parsed.username is not None
                or parsed.password is not None or parsed.path not in ("", "/")
                or parsed.query or parsed.fragment):
            return None
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except (ValueError, TypeError):
        return None
    return (parsed.scheme.lower(), parsed.hostname.lower(), port)


def cross_origin_mutation(request, public_base_url=""):
    """Reject browser requests that originate outside the hosted workspace.

    PayPal's webhook uses separate cryptographic verification and has to accept
    server-to-server calls. A no-Origin request is allowed for authenticated
    command-line/API clients; browser Fetch Metadata still protects newer browsers.
    """
    if request.method not in _UNSAFE_METHODS or request.url.path == "/api/paypal/webhook":
        return False
    site = request.headers.get("sec-fetch-site", "").strip().lower()
    if site in ("cross-site", "same-site"):
        return True
    origin = request.headers.get("origin")
    if origin is None:
        return False
    supplied = _parsed_origin(origin)
    allowed = {_parsed_origin(str(request.base_url)), _parsed_origin(public_base_url)}
    allowed.discard(None)
    return supplied is None or supplied not in allowed


def protect_response(response, path):
    """Avoid caching private demo data and constrain browser embedding/features."""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
    # Public approved JavaScript may be cached only according to the
    # explicit application policy. Failed auth for OTHER static resources
    # must not be cached (even by intermediary browsers/proxies).
    private_asset_denied = path.startswith("/static/") and response.status_code >= 400
    if (path.startswith("/api/") or private_asset_denied
            or path in ("/workspace", "/participant", "/health")) and (
        "cache-control" not in response.headers
    ):
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
    return response
