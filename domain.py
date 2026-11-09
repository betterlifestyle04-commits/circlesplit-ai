"""Deterministic, money-safe allocation. All amounts are integral cents."""
from decimal import Decimal, InvalidOperation

def cents(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Invalid money amount")
    if not amount.is_finite() or amount <= 0 or amount.as_tuple().exponent < -2:
        raise ValueError("Amount must be positive with at most two decimal places")
    result = int(amount * 100)
    if result > 10_000_000:
        raise ValueError("Above demo expense limit")
    return result

def allocate(total_cents, people, strategy="equal"):
    """Largest remainders with stable ID ties; cannot create or lose a cent.

    Validate at the calculation boundary as well as at HTTP and database layers.
    This keeps the hosted settlement math aligned with the browser-only demo:
    never coerce floats, booleans, string IDs or fractional weights into money.
    """
    if (type(total_cents) is not int or total_cents < 0
            or total_cents > (2**53 - 1) // 10
            or not isinstance(people, (list, tuple))
            or not 1 <= len(people) <= 200
            or strategy not in ("equal", "weighted")):
        raise ValueError("Invalid allocation")

    checked = []
    seen = set()
    for person in people:
        try:
            person_id = person["id"]
            weight = person["weight"]
        except (KeyError, IndexError, TypeError):
            raise ValueError("Invalid participant record") from None
        if (type(person_id) is not int or person_id < 1
                or person_id > 2**53 - 1 or person_id in seen
                or type(weight) is not int or not 1 <= weight <= 10):
            raise ValueError("Invalid participant record")
        seen.add(person_id)
        checked.append((person_id, weight))
    ordered = sorted(checked)
    weights = [1 if strategy == "equal" else weight for _, weight in ordered]
    divisor = sum(weights)
    shares = [total_cents * w // divisor for w in weights]
    left = total_cents - sum(shares)
    ranking = sorted(
        range(len(ordered)),
        key=lambda i: (-(total_cents * weights[i] % divisor), ordered[i][0])
    )
    for i in ranking[:left]:
        shares[i] += 1
    result = {person_id: share for (person_id, _), share in zip(ordered, shares)}
    assert sum(result.values()) == total_cents
    return result
