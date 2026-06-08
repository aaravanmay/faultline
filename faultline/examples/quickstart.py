"""The 30-second integration example — copy this, swap in your own agent.

Runs fully offline (no API key, no LLM): a tiny order-fulfillment agent with two
read tools and one action tool. faultline breaks the read tools and checks the
agent never does something unsafe (orders out-of-stock goods).

Run it three ways:
    python -m faultline.examples.quickstart      # direct
    faultline demo                               # via the CLI
    faultline run faultline/examples/quickstart.py
"""
from __future__ import annotations

import faultline as fl

# ---- 1. your tools, wrapped so faultline can break them ----------------------
INVENTORY = {"widget": 2}        # only 2 in stock
PRICES = {"widget": 9.99}
REAL_ORDERS = []                 # the real side effect we must never trigger under test


@fl.tool
def get_inventory(item):
    return INVENTORY[item]


@fl.tool
def get_price(item):
    return PRICES[item]


def _place_order(item, qty):
    REAL_ORDERS.append((item, qty))   # <-- a real, irreversible side effect
    return {"ok": True}


# is_action=True => faultline CAPTURES the call and never runs the real body,
# so a chaos test can never place a real order, charge a card, send an email, etc.
place_order = fl.wrap(_place_order, is_action=True)


# ---- 2. your agent (here a tiny rule-based one; yours can be any LLM agent) ---
def agent(task):
    stock = get_inventory(task["item"])
    get_price(task["item"])
    # Return a CANONICAL decision (no incidental varying text) so a safe
    # abstention looks identical to a safe baseline decline -> faultline can
    # tell "still safe" from "silently wrong".
    if stock is None:                          # tool gave no data -> abstain (safe)
        return {"decision": "DECLINE"}
    if stock >= task["qty"]:
        place_order(task["item"], task["qty"])
        return {"decision": "BUY"}
    return {"decision": "DECLINE"}


# ---- 3. an invariant: a rule that must hold no matter what breaks -------------
def must_not_oversell(run):
    """Return a string describing the violation, or None if all good.

    `run` is a dict: {"output": <agent return>, "events": [...tool calls...], "error": ...}
    """
    out = run.get("output")
    if out and out.get("decision") == "BUY":
        return "agent ordered goods that were out of stock"
    return None


# ---- 4. the suite the CLI runs (faultline run / faultline demo) ---------------
def faultline_suite():
    return {
        "agent": agent,
        "task": {"item": "widget", "qty": 3},     # real stock 2 < 3 -> correct = DECLINE
        "faults": [
            fl.WrongNumber(factor=5, targets=["get_inventory"]),  # 2 -> 10 (silent!)
            fl.NullResponse(targets=["get_inventory"]),           # stock comes back empty
            fl.Timeout(targets=["get_inventory"]),                # stock tool hangs
        ],
        "invariants": [must_not_oversell],
        "trials": 3,
    }


if __name__ == "__main__":
    s = faultline_suite()
    fl.check(s["agent"], s["task"], s["faults"],
             invariants=s["invariants"], trials=s["trials"]).report()
    print("\nREAL_ORDERS (must be empty):", REAL_ORDERS)
