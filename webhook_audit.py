"""Aggregate audit of *locally received*, signature-verified PayPal Sandbox hooks.

This is neither an external PayPal ledger nor evidence that unknown
provider events do not exist. Only aggregate counts leave the backend.
"""

OUTCOMES = (
    "capture_recorded",
    "capture_already_recorded",
    "unmatched_order",
    "missing_order_reference",
    "amount_or_currency_mismatch",
    "invalid_capture_payload",
    "ignored_event_type",
    "legacy_unclassified",
)
REQUIRES_REVIEW = (
    "unmatched_order",
    "missing_order_reference",
    "amount_or_currency_mismatch",
    "invalid_capture_payload",
    "legacy_unclassified",
)


def signed_webhook_audit(connection):
    """Read every locally recorded signed event, never inspect remote PayPal."""
    counts = {name: 0 for name in OUTCOMES}
    for row in connection.execute(
        "SELECT outcome, COUNT(*) AS amount FROM webhook_events GROUP BY outcome"
    ):
        key = row["outcome"]
        if key not in counts:
            # Existing/externally modified database values must not appear
            # as untrusted names in the client or silently disappear.
            key = "legacy_unclassified"
        counts[key] += int(row["amount"])
    return {
        "mode": "PAYPAL_SANDBOX",
        "source": "current_local_sqlite_signed_events_only",
        "total_events": sum(counts.values()),
        "manual_review_events": sum(counts[key] for key in REQUIRES_REVIEW),
        "outcomes": counts,
        "notice": (
            "Counts cover only signed webhook events retained in the current "
            "local SQLite file. An unmatched capture may reflect an order "
            "creation response still in flight or a lost database record. "
            "No automatic retries, capture attempts, provider lookups or "
            "manual settlement are performed. Check PayPal Sandbox and "
            "the separate payment recovery view before taking action."
        ),
    }
