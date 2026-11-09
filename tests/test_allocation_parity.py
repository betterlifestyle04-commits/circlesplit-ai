"""Read-only integrity checks for the shared exact-cent allocation contract.

The backend makes Sandbox amounts; the public JS module models fictional plans.
They must agree for every valid deterministic input, but these tests never call
PayPal, mutate the database, or assert a live provider capture.
"""
import json
import random
import subprocess
from pathlib import Path

import pytest

from domain import allocate


ROOT = Path(__file__).resolve().parents[1]
SAFE_CENTS = (2**53 - 1) // 10


@pytest.mark.parametrize("invalid", [
    None, False, True, -1, 1.5, "100", float("nan"), float("inf"),
    SAFE_CENTS + 1,
])
def test_backend_rejects_noninteger_or_unsafe_cents(invalid):
    with pytest.raises(ValueError, match="Invalid allocation"):
        allocate(invalid, [{"id": 1, "weight": 1}])


@pytest.mark.parametrize("invalid_people", [
    None, [], "not people", [None], [42],
    [{}], [{"id": 1}], [{"weight": 1}],
    [{"id": 1, "weight": 1}, {"id": 1, "weight": 2}],
    [{"id": True, "weight": 1}], [{"id": "2", "weight": 1}],
    [{"id": 0, "weight": 1}], [{"id": 2**53, "weight": 1}],
    [{"id": 1, "weight": True}], [{"id": 1, "weight": 1.5}],
    [{"id": 1, "weight": "2"}], [{"id": 1, "weight": 11}],
    [{"id": i + 1, "weight": 1} for i in range(201)],
])
def test_backend_rejects_malformed_participants(invalid_people):
    with pytest.raises(ValueError, match="Invalid"):
        allocate(100, invalid_people)


def test_backend_is_exact_order_independent_and_never_modifies_caller():
    people = [{"id": 5, "weight": 3}, {"id": 2, "weight": 2},
              {"id": 8, "weight": 1}]
    before = json.dumps(people)
    assert allocate(101, people, "weighted") == {
        2: 34, 5: 50, 8: 17
    }
    assert allocate(101, list(reversed(people)), "weighted") == allocate(
        101, people, "weighted"
    )
    assert json.dumps(people) == before
    assert allocate(0, people, "equal") == {2: 0, 5: 0, 8: 0}


def test_browser_and_backend_agree_on_400_seeded_cent_allocations():
    """Invoke the real JS module once; compare exact ID-sorted cents to Python."""
    rng = random.Random(20261109)
    cases = [
        {"total": 1000, "people": [{"id": 3, "weight": 1},
                                   {"id": 1, "weight": 1},
                                   {"id": 2, "weight": 1}],
         "strategy": "equal"},
        {"total": 101, "people": [{"id": 5, "weight": 3},
                                  {"id": 2, "weight": 2},
                                  {"id": 8, "weight": 1}],
         "strategy": "weighted"},
    ]
    totals = [0, 1, 2, 99, 100, 101, 1000, 10001, 10000000,
              2000000000, SAFE_CENTS]
    for _ in range(398):
        count = rng.randint(1, 200)
        people = [
            {"id": i + 1, "weight": rng.randint(1, 10)}
            for i in range(count)
        ]
        rng.shuffle(people)
        cases.append({
            "total": rng.choice(totals + [rng.randint(0, 2000000000)]),
            "people": people,
            "strategy": rng.choice(["equal", "weighted"]),
        })
    javascript = r"""
const fs = require("node:fs");
const { exactSplit } = require("./static/public_recovery.js");
const cases = JSON.parse(fs.readFileSync(0, "utf8"));
const values = cases.map(c => exactSplit(c.total, c.people, c.strategy));
process.stdout.write(JSON.stringify(values));
"""
    process = subprocess.run(
        ["node", "-e", javascript], input=json.dumps(cases), text=True,
        capture_output=True, check=True, timeout=20, cwd=ROOT
    )
    browser_shares = json.loads(process.stdout)
    assert len(browser_shares) == 400
    for index, (case, frontend) in enumerate(zip(cases, browser_shares)):
        people_before = json.dumps(case["people"])
        backend = allocate(case["total"], case["people"], case["strategy"])
        assert frontend == list(backend.values()), (
            f"Public/backend allocation differs at deterministic case {index}"
        )
        assert sum(frontend) == case["total"]
        assert all(isinstance(c, int) and c >= 0 for c in frontend)
        assert json.dumps(case["people"]) == people_before
