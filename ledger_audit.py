"""Read-only global integrity checks for the LOCAL PayPal Sandbox ledger.

No provider calls, credentials, identity assumptions or state mutations.
Unresolved sandbox orders are counted separately from integrity violations.
"""
from collections import Counter


def local_ledger_audit(c, max_findings=100):
    """Return bounded findings but complete counts across all local records."""
    counts = Counter()
    findings = []
    processed = 0

    def issue(code, *, payment_id=None, event_id=None, person_id=None):
        counts[code] += 1
        if len(findings) < max_findings:
            findings.append({
                "code": code, "payment_id": payment_id,
                "event_id": event_id, "person_id": person_id,
            })

    payments = c.execute(
        """SELECT pay.id,pay.event_id,pay.person_id,pay.status,
                  pay.amount_cents,pay.order_id,pay.capture_id,
                  person.id AS linked_person,person.event_id AS person_event,
                  person.share_cents,person.status AS person_status,
                  evt.id AS linked_event
           FROM payments pay
           LEFT JOIN people person ON person.id=pay.person_id
           LEFT JOIN events evt ON evt.id=pay.event_id
           ORDER BY pay.id"""
    ).fetchall()
    per_person = Counter()
    completed_by_person = Counter()
    capture_seen = set()
    unresolved = 0
    for pay in payments:
        processed += 1
        pid, eid, payid = pay["person_id"], pay["event_id"], pay["id"]
        status = pay["status"]
        per_person[pid] += 1
        if status != "completed":
            unresolved += 1
        ids = {"payment_id":payid,"event_id":eid,"person_id":pid}
        if pay["linked_event"] is None:
            issue("missing_event",**ids)
        if pay["linked_person"] is None:
            issue("missing_participant",**ids)
        elif pay["person_event"] != eid:
            issue("payment_event_mismatch",**ids)
        if type(pay["amount_cents"]) is not int or pay["amount_cents"] <= 0:
            issue("invalid_payment_amount",**ids)
        if pay["linked_person"] is not None and pay["amount_cents"] != pay["share_cents"]:
            issue("payment_amount_mismatch",**ids)
        if status not in ("creating","created","capturing","completed"):
            issue("invalid_payment_status",**ids)
        if status in ("created","capturing","completed") and not pay["order_id"]:
            issue("missing_paypal_order_id",**ids)
        if status == "completed":
            if not pay["capture_id"]:
                issue("completed_without_capture",**ids)
            else:
                if pay["capture_id"] in capture_seen:
                    issue("duplicate_capture_id",**ids)
                capture_seen.add(pay["capture_id"])
                if pay["linked_person"] is not None and pay["person_event"] == eid:
                    completed_by_person[pid] += 1
            if pay["linked_person"] is not None and pay["person_status"] != "sandbox_paid":
                issue("completed_person_not_paid",**ids)
        elif pay["capture_id"]:
            issue("capture_on_incomplete_payment",**ids)
        if pay["linked_person"] is not None and pay["person_status"] == "demo_paid":
            issue("simulated_person_has_paypal_order",**ids)

    for pid, count in per_person.items():
        if count > 1:
            issue("multiple_paypal_orders_for_person",person_id=pid)

    for person in c.execute(
        "SELECT id,event_id,status FROM people ORDER BY id"
    ):
        if person["status"] == "sandbox_paid" and completed_by_person[person["id"]] == 0:
            issue("paid_person_without_capture",
                  event_id=person["event_id"],person_id=person["id"])

    return {
        "mode": "PAYPAL_SANDBOX",
        "status": "needs_review" if counts else "locally_consistent",
        "payment_records_checked": processed,
        "unresolved_orders": unresolved,
        "issue_count": sum(counts.values()),
        "issue_counts": dict(sorted(counts.items())),
        "findings": findings,
        "findings_truncated": sum(counts.values()) > len(findings),
        "limitations": ("Checks local SQLite record consistency only. "
                        "Unresolved orders are not proof of failure. "
                        "No external PayPal status, payment settlement, "
                        "identity verification or database durability is attested."),
    }
