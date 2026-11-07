"""Strict per-page Content-Security-Policy for public CircleSplit surfaces.

Scripts in the public homepage are first-party, and its only inline script
is authorized by an exact SHA-256 of its *deployed* bytes. No wildcard,
unsafe-inline script permission, third-party script, or dynamic user input.
A static judge guide is intentionally allowed same-origin GET fetches for
the health badge; the public planning demo is entirely browser-local.
The private invitation page needs same-origin bearer-authenticated API calls
and a client-side calendar download but not arbitrary inline JavaScript.

Read source at process start so CSP cannot silently drift between
deployment versions. The public files are repository-owned, immutable
during a single deployment. The organizer workspace's many historical
inline handlers are NOT covered by this strict policy.
"""
import base64
import hashlib
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
_INLINE_SCRIPT = re.compile(
    r"<script\b(?![^>]*\bsrc\s*=)[^>]*>(.*?)</script\s*>",
    re.IGNORECASE | re.DOTALL,
)


def inline_script_hashes(html):
    if not isinstance(html, str):
        raise ValueError("Page source must be text")
    codes = _INLINE_SCRIPT.findall(html)
    return tuple(
        "'sha256-" + base64.b64encode(
            hashlib.sha256(source.encode("utf-8")).digest()
        ).decode("ascii") + "'"
        for source in codes
    )


def page_csp(html, *, allow_health=False):
    """No remote scripts or inline event handlers, including future additions."""
    scripts = inline_script_hashes(html)
    parts = (
        "default-src 'none'",
        "base-uri 'none'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "form-action 'none'",
        "script-src 'self'" + (" " + " ".join(scripts) if scripts else ""),
        # Existing public HTML uses inline stylesheet and small style attrs;
        # keep CSS compatible but do not allow inline executable JavaScript.
        "style-src 'self' 'unsafe-inline'",
        "img-src 'self' data:",
        "font-src 'self'",
        "connect-src 'self'" if allow_health else "connect-src 'none'",
        "worker-src 'none'",
    )
    return "; ".join(parts)


PUBLIC_PAGE_CSP = {
    "/": page_csp((ROOT / "static" / "public.html").read_text(encoding="utf-8")),
    "/judge": page_csp(
        (ROOT / "static" / "judge.html").read_text(encoding="utf-8"),
        allow_health=True,
    ),
    "/participant": page_csp(
        (ROOT / "static" / "participant.html").read_text(encoding="utf-8"),
        allow_health=True,  # private, same-origin invitation APIs
    ),
}
