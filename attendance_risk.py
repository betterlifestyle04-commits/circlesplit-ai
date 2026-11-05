"""Deterministic, read-only attendance stress scenarios.

This is an illustrative adverse roster assumption, not a probability estimate
or a promise that a particular attendee will cancel. It never edits actual
participant shares, payment state, invitations, or approvals.
"""
from domain import allocate


def attendance_stress_curve(total_cents, people, strategy, maximum_absent, max_share_cents):
    """Keep one highest-weight member and progressively remove other heavy weights.

    The algorithm models one explicit, reproducible adverse roster rather than
    claiming to enumerate every possible subset of absent members. Equal splits
    use stable member IDs as tie breakers. All projected shares use the same
    exact-cent largest-remainder allocator as live event planning.
    """
    if (type(total_cents) is not int or total_cents < 0
            or type(maximum_absent) is not int or not 0 <= maximum_absent <= 20
            or type(max_share_cents) is not int or not 1 <= max_share_cents <= 10_000_000
            or strategy not in ("equal", "weighted")
            or not isinstance(people, list) or not 1 <= len(people) <= 200):
        raise ValueError("Invalid attendance stress inputs")
    ids = [p["id"] for p in people]
    if len(set(ids)) != len(ids):
        raise ValueError("Duplicate participant IDs")
    for p in people:
        if (type(p["id"]) is not int or type(p["weight"]) is not int
                or not 1 <= p["weight"] <= 10):
            raise ValueError("Invalid participant for attendance stress")

    weight = lambda p: 1 if strategy == "equal" else p["weight"]
    anchor = min(people, key=lambda p: (-weight(p), p["id"]))
    candidates = sorted(
        (p for p in people if p["id"] != anchor["id"]),
        key=lambda p: (-weight(p), -p["id"]),
    )
    tested_maximum = min(maximum_absent, len(candidates))
    baseline = allocate(total_cents, people, strategy)
    initial_peak = max(baseline.values())
    # New fictional attendees have weight 1 and receive distinct IDs beyond
    # all existing IDs, including the members removed in the stress scenario.
    next_id = max(ids)

    first_breach = None
    rows = []
    for absent_count in range(tested_maximum + 1):
        absent_ids = {p["id"] for p in candidates[:absent_count]}
        remaining = [p for p in people if p["id"] not in absent_ids]
        shares = allocate(total_cents, remaining, strategy)
        highest = max(shares.values())
        lowest = min(shares.values())
        over = highest > max_share_cents
        if over and first_breach is None:
            first_breach = absent_count

        # Exhaustively test the bounded 0..50 additional-attendee counts rather
        # than assuming largest-remainder allocations are strictly monotonic.
        # This preserves exact-cent correctness for weighted group allocations.
        replacement_limit = min(50, 200 - len(remaining))
        best_peak, best_count, feasible_count = highest, 0, (0 if not over else None)
        tested = 1
        if over:
            projected_people = list(remaining)
            for count in range(1, replacement_limit + 1):
                projected_people.append({"id": next_id + count, "weight": 1})
                projected_shares = allocate(total_cents, projected_people, strategy)
                projected_peak = max(projected_shares.values())
                tested += 1
                if (projected_peak, count) < (best_peak, best_count):
                    best_peak, best_count = projected_peak, count
                if projected_peak <= max_share_cents:
                    feasible_count = count
                    best_peak, best_count = projected_peak, count
                    break
        rows.append({
            "replacements_feasible": feasible_count is not None,
            "minimum_replacements_needed": feasible_count,
            "best_replacement_count": best_count,
            "best_replacement_largest_share_cents": best_peak,
            "replacement_gap_cents": max(0, best_peak - max_share_cents),
            "maximum_replacements_considered": replacement_limit,
            "replacement_candidates_tested": tested,
            "absent_people": absent_count,
            "remaining_people": len(remaining),
            "largest_share_cents": highest,
            "smallest_share_cents": lowest,
            "largest_share_increase_cents": highest - initial_peak,
            "over_target": over,
        })
    return {
        "scenario_rule": "retain_highest_weight_remove_next_highest",
        "tested_maximum_absent": tested_maximum,
        "current_largest_share_cents": initial_peak,
        "first_target_breach_at_absences": first_breach,
        "projections": rows,
    }
