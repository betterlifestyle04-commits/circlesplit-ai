"""Per-process provider-cost protection for the hosted hackathon sandbox.

Counts attempts by shared authenticated demo role, not individual identity.
This is intentionally a conservative cost guard, not a production-grade
distributed rate limiter or user-specific quota system.
"""
from collections import deque
from math import ceil
import re
from threading import Lock
from time import monotonic


# A modest shared budget per 60 seconds for the controlled testing workspace.
# Ordinary planning endpoints, public pages and signed webhooks are exempt.
POLICIES = {
    "ai": (12, 60),
    "checkout": (6, 60),
    "reconciliation": (30, 60),
}
_ORDER = re.compile(r"^/api/paypal/orders/\d+/\d+$")
_STATUS = re.compile(r"^/api/paypal/order-status/[A-Za-z0-9-]{5,50}$")
_PLAN = re.compile(r"^/api/ai/plan/\d+$")


def provider_group(method, path):
    """Classify sensitive outbound-provider actions without matching lookalike paths."""
    if method != "POST":
        return None
    if path == "/api/ai/parse" or _PLAN.fullmatch(path):
        return "ai"
    if _ORDER.fullmatch(path):
        return "checkout"
    if path == "/api/paypal/capture" or _STATUS.fullmatch(path):
        return "reconciliation"
    return None


class ProviderLimiter:
    """Thread-safe sliding windows. Never stores IPs, tokens or request bodies."""

    def __init__(self, clock=monotonic):
        self.clock = clock
        self.lock = Lock()
        self.windows = {}

    def attempt(self, role, group):
        """Return (allowed, remaining, retry_after_seconds, limit)."""
        limit, window_seconds = POLICIES[group]
        stamp = self.clock()
        key = (role, group)
        with self.lock:
            timestamps = self.windows.setdefault(key, deque())
            cutoff = stamp - window_seconds
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
            if len(timestamps) >= limit:
                retry = max(1, ceil(timestamps[0] + window_seconds - stamp))
                return False, 0, retry, limit
            timestamps.append(stamp)
            return True, limit - len(timestamps), 0, limit
