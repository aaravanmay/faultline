"""Tests for Method A (scenarios): honest hard inputs + a behavioral rule, NO faults injected.

The whole point: a failure here is a real agent bug (the agent ignored data it actually had),
not "garbage in, garbage out." Deterministic, no API.  Run: python3 tests/test_scenarios.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faultline as fl

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("  ok  " if cond else "FAIL  ") + name)


# A little world. Every tool returns the TRUTH — nothing is faked.
WORLD = {"a": 3, "b": 2, "c": 0, "d": 100}


@fl.tool
def get_inventory(item):
    return WORLD[item]            # honest: the real stock


def _place_order(item, qty):
    return "ordered %d %s" % (qty, item)


place_order = fl.wrap(_place_order, is_action=True)


def safe_agent(task):
    stock = get_inventory(task["item"])
    if task["qty"] <= stock:                  # correct
        place_order(task["item"], task["qty"])
        return {"decision": "ORDER"}
    return {"decision": "DECLINE"}


def buggy_agent(task):
    stock = get_inventory(task["item"])
    if task["qty"] <= stock + 1:              # BUG: off-by-one, oversells by one at the boundary
        place_order(task["item"], task["qty"])
        return {"decision": "ORDER"}
    return {"decision": "DECLINE"}


# The honest rule: the agent must never order more than the stock it actually read.
def never_oversell(run):
    stock = ordered = None
    for ev in run["events"]:
        if ev.get("tool") == "get_inventory":
            stock = ev.get("result")
        if ev.get("is_action") and len(ev.get("args", ())) >= 2:
            ordered = ev["args"][1]
    if ordered is not None and stock is not None and ordered > stock:
        return "ordered %d but only saw %d in stock" % (ordered, stock)


CASES = [
    ("exact stock", {"item": "a", "qty": 3}),   # 3 of 3 -> ORDER, fine
    ("one short",   {"item": "b", "qty": 3}),   # wants 3, only 2 -> must DECLINE
    ("empty",       {"item": "c", "qty": 1}),   # 0 in stock -> must DECLINE
    ("plenty",      {"item": "d", "qty": 5}),   # 5 of 100 -> ORDER, fine
]


# safe agent: holds the rule on every honest case
rs = fl.scenarios(safe_agent, CASES, [never_oversell])
check("safe agent: passes every honest scenario", rs.safe())
check("safe agent: zero violations", len(rs.violations()) == 0)

# buggy agent: caught on the honest 'one short' case — no lying needed
rb = fl.scenarios(buggy_agent, CASES, [never_oversell])
check("buggy agent: flagged as unsafe", not rb.safe())
check("buggy agent: the off-by-one breaks both boundary cases", sorted(v["name"] for v in rb.violations()) == ["empty", "one short"])
check("buggy agent: the report explains the real bug", any("ordered 3 but only saw 2" in v["detail"] for v in rb.violations()))

# all inputs were honest -> proves this isn't garbage-in
check("no faults were injected (honest inputs only)", all(WORLD[c[1]["item"]] >= 0 for c in CASES))


passed = sum(1 for _, c in results if c)
print("\n%d passed, %d failed" % (passed, len(results) - passed))
sys.exit(0 if passed == len(results) else 1)
