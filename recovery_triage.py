"""Read-only triage of the *local* PayPal Sandbox order ledger.

A triage category is not a PayPal provider state, money receipt, loss
estimate, or authorization to retry a charge. All output is aggregated;
never return names, order/capture IDs, request keys, or invitations.
"""
from datetime import datetime, timedelta, timezone


CATEGORIES = (
    "inconsistent_local_record",
    "unknown_order_creation",
    "uncertain_capture_attempt",
    "awaiting_provider_confirmation",
    "locally_completed",
)


def recovery_risk_summary(connection, current=None):
    """Return an all-record summary independent of the recovery page size.

    SQLite performs the classification and aggregation to avoid shipping
    entire ledgers into Python. The 60-minute cutoff is a *review prompt*,
    never a request timeout or an order-expiry assumption.
    """
    current = current or datetime.now(timezone.utc)
    if current.tzinfo is None:
        raise ValueError("Recovery assessment requires a timezone-aware clock")
    cutoff = (current.astimezone(timezone.utc) - timedelta(minutes=60)).isoformat()
    rows = connection.execute(
        """
        WITH classified AS (
          SELECT
            CASE
              WHEN e.id IS NULL OR a.id IS NULL OR a.event_id != p.event_id
                OR p.amount_cents IS NULL OR p.amount_cents <= 0
                OR p.status NOT IN ('creating','created','capturing','completed')
                OR (p.status IN ('created','capturing','completed')
                    AND (p.order_id IS NULL OR p.order_id = ''))
                OR (p.status != 'completed'
                    AND p.capture_id IS NOT NULL AND p.capture_id != '')
                OR (p.status = 'completed'
                    AND (p.capture_id IS NULL OR p.capture_id = ''))
              THEN 'inconsistent_local_record'
              WHEN p.status = 'creating' THEN 'unknown_order_creation'
              WHEN p.status = 'capturing' THEN 'uncertain_capture_attempt'
              WHEN p.status = 'created' THEN 'awaiting_provider_confirmation'
              ELSE 'locally_completed'
            END AS category,
            CASE WHEN p.amount_cents > 0 THEN p.amount_cents ELSE 0 END AS face_cents,
            julianday(p.created) AS created_day
          FROM payments AS p
          LEFT JOIN events AS e ON e.id = p.event_id
          LEFT JOIN people AS a ON a.id = p.person_id
        )
        SELECT category,COUNT(*) AS count,COALESCE(SUM(face_cents),0) AS face_cents,
               SUM(CASE WHEN created_day IS NOT NULL
                        AND created_day <= julianday(?) THEN 1 ELSE 0 END) AS old_count,
               SUM(CASE WHEN created_day IS NULL THEN 1 ELSE 0 END) AS unknown_age_count
        FROM classified
        GROUP BY category
        """,
        (cutoff,),
    ).fetchall()
    counts = {key: 0 for key in CATEGORIES}
    older = {key: 0 for key in CATEGORIES}
    value = {key: 0 for key in CATEGORIES}
    invalid_timestamp = 0
    for row in rows:
        category = row["category"]
        if category not in counts:
            raise ValueError("Unexpected recovery category")
        counts[category] = int(row["count"])
        older[category] = int(row["old_count"])
        value[category] = int(row["face_cents"])
        invalid_timestamp += int(row["unknown_age_count"])
    open_categories = CATEGORIES[:-1]
    attention_count = sum(counts[key] for key in open_categories)
    critical_count = sum(counts[key] for key in open_categories[:3])
    state = ("needs_manual_review" if critical_count else
             "pending_provider_confirmation" if attention_count else
             "no_local_unresolved_records")
    return {
        "mode": "PAYPAL_SANDBOX",
        "source": "current_local_sqlite_only",
        "status": state,
        "total_records": sum(counts.values()),
        "attention_count": attention_count,
        "priority_review_count": critical_count,
        "older_than_60_minutes": sum(older[key] for key in open_categories),
        "unparseable_created_timestamps": invalid_timestamp,
        "unverified_request_face_value_cents": sum(value[key] for key in open_categories),
        "categories": counts,
        "notice": (
            "This aggregates current local Sandbox request records only. "
            "An unresolved request amount is not a loss, debt, or settled payment. "
            "An order/capture may exist at PayPal even if missing locally, "
            "especially after an ephemeral SQLite reset. Review uncertain "
            "creation/capture responses and inconsistent records using PayPal "
            "Sandbox evidence; never blindly create or capture a second time. "
            "An age over 60 minutes is an investigation prompt, not an expiry."
        ),
    }
