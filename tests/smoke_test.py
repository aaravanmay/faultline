"""End-to-end smoke test — no network, no LLM, no API keys.

Proves the whole mechanism on a tiny shopping agent:
  - baseline (no faults) gives the correct answer
  - a WRONG-but-plausible tool value makes the agent SILENTLY sell out-of-stock
  - a timeout / server error makes it CRASH
  - the resilience score is computed and the report renders

Run:  python3 tests/smoke_test.py   (expect: RESULT: <n> passed, 0 failed)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import faultline.legacy as fl              # legacy v0.1 oracle API
from faultline.legacy import PASS, SILENT, CRASH

# --- a tiny "agent" that uses two tools to decide whether to sell ---
INVENTORY = {"widget": 2}     # only 2 in stock
PRICES = {"widget": 9.99}


@fl.tool
def get_inventory(item):
    return INVENTORY[item]


@fl.tool
def get_price(item):
    return PRICES[item]


def shopping_agent(task):
    """Decide whether to fulfill an order. Naive — trusts its tools blindly,
    exactly like most real agents."""
    item, qty = task["item"], task["qty"]
    stock = get_inventory(item)
    price = get_price(item)
    if stock >= qty:
        return {"decision": "BUY", "total": round(price * qty, 2)}
    return {"decision": "DECLINE", "reason": "out of stock"}


def oracle(output):
    # Correct answer for "buy 3 widgets" when only 2 are in stock = DECLINE.
    return output is not None and output.get("decision") == "DECLINE"


PASSED = 0
FAILED = 0


def check(name, cond):
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print("  ✓ %s" % name)
    else:
        FAILED += 1
        print("  ✗ FAIL: %s" % name)


def status_of(result, fault_name):
    for n, s, _ in result.rows:
        if n == fault_name:
            return s
    return None


def main():
    print("faultline smoke test")
    print("-" * 40)

    task = {"item": "widget", "qty": 3}   # ask to buy 3, only 2 exist → should DECLINE

    result = fl.chaos(shopping_agent, task, oracle, faults=[
        fl.WrongNumber(factor=5, targets=["get_inventory"]),  # 2 -> 10, silently sells out-of-stock
        fl.Timeout(targets=["get_inventory"]),                # tool hangs
        fl.ServerError(targets=["get_price"]),                # price service 500s
        fl.NullResponse(targets=["get_inventory"]),           # stock comes back None
    ])

    check("baseline is correct (agent declines when out of stock)", result.baseline_ok)
    check("WrongNumber causes a SILENT wrong answer (sells out-of-stock)",
          status_of(result, "wrong-number") == SILENT)
    check("Timeout makes the agent CRASH (no error handling)",
          status_of(result, "timeout") == CRASH)
    check("ServerError makes the agent CRASH",
          status_of(result, "server-error") == CRASH)
    check("NullResponse makes the agent CRASH",
          status_of(result, "null-response") == CRASH)
    check("at least one silent failure was found", len(result.silent_failures) >= 1)
    check("resilience score is 0% (agent handled none of them)", result.resilience == 0.0)

    # the report should render
    text = result.report()
    check("report renders with score + silent-failure warning",
          "Resilience score" in text and "SILENT" in text)

    print("-" * 40)
    print("RESULT: %d passed, %d failed" % (PASSED, FAILED))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
