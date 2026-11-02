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
    """Largest remainders with stable ID ties; cannot create or lose a cent."""
    if total_cents < 0 or not people or strategy not in ("equal", "weighted"):
        raise ValueError("Invalid allocation")
    ordered = sorted(people, key=lambda x: x["id"])
    weights = [1 if strategy == "equal" else int(p["weight"]) for p in ordered]
    if any(w < 1 or w > 10 for w in weights):
        raise ValueError("Invalid participant weight")
    divisor = sum(weights)
    shares = [total_cents * w // divisor for w in weights]
    left = total_cents - sum(shares)
    ranking = sorted(range(len(ordered)), key=lambda i: (-(total_cents * weights[i] % divisor), ordered[i]["id"]))
    for i in ranking[:left]:
        shares[i] += 1
    result = {p["id"]: share for p, share in zip(ordered, shares)}
    assert sum(result.values()) == total_cents
    return result
