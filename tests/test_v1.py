"""test_v1.py — self-contained v1 API test for faultline.

Targets the new runner/trace/faults API (not the legacy faultline.__init__ API).
Run: python3 tests/test_v1.py
     (from repo root: python3 Claude/faultline/tests/test_v1.py)
"""
from __future__ import annotations

import os
import sys

# Make `import faultline` resolve to the package in the repo, regardless of cwd.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from faultline.trace import tool, wrap, run_once
from faultline.runner import check as fl_check
from faultline.faults import WrongNumber, NullResponse, Timeout

# ---------------------------------------------------------------------------
# Inline demo agent — self-contained, no examples module.
# ---------------------------------------------------------------------------

INVENTORY = {"widget": 2}   # only 2 in stock
PRICES = {"widget": 9.99}
REAL_ORDERS: list = []       # must stay empty — place_order is an action tool


@tool
def get_inventory(item):
    return INVENTORY[item]


@tool
def get_price(item):
    return PRICES[item]


def _place_order(item, qty):
    REAL_ORDERS.append((item, qty))
    return {"ok": True}


place_order = wrap(_place_order, is_action=True)


def agent(task):
    """Decide whether to BUY or DECLINE. Handles a None stock gracefully."""
    item, qty = task["item"], task["qty"]
    stock = get_inventory(item)
    if stock is None:
        return {"decision": "DECLINE", "reason": "couldn't verify", "unverified": True}
    price = get_price(item)
    if stock >= qty:
        place_order(item, qty)
        return {"decision": "BUY", "total": round(price * qty, 2)}
    return {"decision": "DECLINE", "reason": "out of stock"}


# Task: buy 3 widgets; only 2 exist → correct answer is DECLINE.
TASK = {"item": "widget", "qty": 3}

# ---------------------------------------------------------------------------
# Minimal test harness.
# ---------------------------------------------------------------------------

PASSED = 0
FAILED = 0


def check(name: str, cond: bool) -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("  ✓ %s" % name)
    else:
        FAILED += 1
        print("  ✗ FAIL: %s" % name)


def find_row(rows: list, fault_name: str) -> "dict | None":
    for r in rows:
        if r["fault"] == fault_name:
            return r
    return None


# ---------------------------------------------------------------------------
# Run.
# ---------------------------------------------------------------------------

def main() -> int:
    print("faultline v1 API test")
    print("-" * 50)

    # --- 1. Baseline correctness ---
    baseline_run = run_once(agent, TASK)
    check(
        "baseline output decision == DECLINE (no fault, agent correct)",
        baseline_run["output"] is not None
        and baseline_run["output"].get("decision") == "DECLINE",
    )

    # --- 2. Run full check ---
    faults = [
        WrongNumber(factor=5, targets=["get_inventory"]),  # 2 -> 10, agent thinks in-stock
        Timeout(targets=["get_inventory"]),                 # raises TimeoutError
        NullResponse(targets=["get_inventory"]),            # agent gets None, handles gracefully
    ]
    res = fl_check(agent, TASK, faults, trials=5)

    wrong_row = find_row(res.rows, "wrong-number")
    timeout_row = find_row(res.rows, "timeout")
    null_row = find_row(res.rows, "null-response")

    # --- 3. WrongNumber -> FAIL (silent failure: agent BUYs when it should DECLINE) ---
    check(
        "WrongNumber row exists",
        wrong_row is not None,
    )
    check(
        "WrongNumber verdict == FAIL (silent failure surfaced)",
        wrong_row is not None and wrong_row["verdict"] == "FAIL",
    )

    # --- 4. Timeout -> CRASH ---
    check(
        "Timeout row exists",
        timeout_row is not None,
    )
    check(
        "Timeout verdict == CRASH",
        timeout_row is not None and timeout_row["verdict"] == "CRASH",
    )

    # --- 5. NullResponse -> PASS (agent's null-guard handles it) ---
    check(
        "NullResponse row exists",
        null_row is not None,
    )
    check(
        "NullResponse verdict == PASS (null-guard works)",
        null_row is not None and null_row["verdict"] == "PASS",
    )

    # --- 6. At least one silent failure surfaced ---
    check(
        "res.silent has >= 1 entry (silent failure detected)",
        len(res.silent) >= 1,
    )

    # --- 7. No real side effects: place_order body never ran ---
    check(
        "REAL_ORDERS == [] (action tool body never executed under test)",
        REAL_ORDERS == [],
    )

    # --- 8. Each row's trials list has length == 5 ---
    all_trial_lengths_correct = all(
        len(r["trials"]) == 5 for r in res.rows
    )
    check(
        "each row's trials list has length 5 (multi-trial ran)",
        all_trial_lengths_correct,
    )

    # --- Bonus: print the engine report for visibility ---
    print()
    res.report()

    print("-" * 50)
    print("RESULT: %d passed, %d failed" % (PASSED, FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
