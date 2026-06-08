"""faultline.examples.shop_agent — demo decision-agent for tripwire-check.

A realistic e-commerce fulfillment agent that:
  - checks stock before ordering
  - handles None gracefully (null-guard)
  - but silently trusts a corrupted inventory count (WrongNumber bug)

Correct answer for {"item": "widget", "qty": 3} with 2 in stock = DECLINE.
WrongNumber(factor=5) turns 2 -> 10, so the agent wrongly buys — silent failure.
"""
from __future__ import annotations

from faultline.trace import tool, wrap
from faultline.faults import WrongNumber, Timeout, NullResponse, ServerError

# ---------------------------------------------------------------------------
# In-memory "database"
# ---------------------------------------------------------------------------

INVENTORY = {"widget": 2}       # only 2 in stock
PRICES = {"widget": 9.99}
REAL_ORDERS: list = []          # proves action tools never really run under test


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@tool
def get_inventory(item: str):
    return INVENTORY[item]


@tool
def get_price(item: str):
    return PRICES[item]


def _place_order(item: str, qty: int):
    """The REAL side effect — must never fire under test."""
    REAL_ORDERS.append((item, qty))
    return {"ok": True}


# wrap as an action tool: real body is NEVER executed during faultline sessions
place_order = wrap(_place_order, is_action=True)


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

def shop_agent(task: dict) -> dict:
    """Decide whether to fulfill an order.

    Guards against None stock (null-guard), but trusts the number it gets —
    so a corrupted count is a silent failure (WrongNumber).
    """
    item = task["item"]
    qty = task["qty"]

    stock = get_inventory(item)

    # Null-guard: if we couldn't verify stock, decline gracefully
    if stock is None:
        return {
            "decision": "DECLINE",
            "reason": "couldn't verify stock",
            "unverified": True,
        }

    price = get_price(item)

    if stock >= qty:
        place_order(item, qty)
        return {"decision": "BUY", "total": round(price * qty, 2)}

    return {"decision": "DECLINE", "reason": "out of stock"}


# ---------------------------------------------------------------------------
# Demo helper
# ---------------------------------------------------------------------------

def demo_scenario():
    """Return (task, faults) for the canonical tripwire-check demo.

    task   : buy 3 widgets when only 2 are in stock → correct answer = DECLINE
    faults : four faults that stress-test the agent in different ways
    """
    task = {"item": "widget", "qty": 3}

    faults = [
        # Silent killer: 2 -> 10, so the agent wrongly buys (FAIL)
        WrongNumber(factor=5, targets=["get_inventory"]),
        # Hard failure: tool hangs — unhandled TimeoutError (CRASH)
        Timeout(targets=["get_inventory"]),
        # Graceful: agent's null-guard catches this (PASS)
        NullResponse(targets=["get_inventory"]),
        # Hard failure: price service 500s — unhandled RuntimeError (CRASH)
        ServerError(targets=["get_price"]),
    ]

    return task, faults
