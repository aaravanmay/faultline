"""A realistic multi-tool agent (a 4-step fulfillment chain) — and the CASCADE silent failure.

Real agents chain tools, so a fault in an early tool propagates through later decisions into the
action. Here a corrupted PRICE flows through the budget check into the order: the agent approves a
purchase that's actually over budget, with no error of its own. faultline catches it. No API key.

    python3 examples/multi_tool_agent.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import faultline as fl

_STOCK = {"WIDGET-9": 500}
_PRICE = {"WIDGET-9": 10.0}      # the TRUE unit price
BUDGET = 1000.0


@fl.tool
def get_stock(sku):
    return {"sku": sku, "units": _STOCK.get(sku, 0)}


@fl.tool
def get_price(sku):
    return {"sku": sku, "unit_price": _PRICE.get(sku, 0.0)}      # faultline will corrupt this


_orders = []


def _place(sku, qty, total):
    _orders.append((sku, qty, total))
    return {"ok": True, "sku": sku, "qty": qty}


place_order = fl.wrap(_place, is_action=True, name="place_order")


def agent(task):
    """The chain: stock -> price -> compute total -> budget check -> order."""
    sku, qty = task["sku"], task["qty"]
    units = get_stock(sku)["units"]
    price = get_price(sku)["unit_price"]
    total = qty * price
    if units >= qty and total <= BUDGET:        # in stock AND within budget -> order
        place_order(sku, qty, total)
        return {"decision": "ordered", "qty": qty, "total": total}
    return {"decision": "declined", "total": total}


def within_true_budget(run):
    """Oracle: never approve an order whose TRUE total exceeds the budget (uses the real price,
    not the corrupted one the agent saw)."""
    true_price = _PRICE["WIDGET-9"]
    for ev in run["events"]:
        if ev.get("is_action") and ev["tool"] == "place_order":
            args = ev.get("args") or []
            qty = args[1] if len(args) >= 2 else 0
            true_total = qty * true_price
            if true_total > BUDGET:
                return ("approved an order whose TRUE total is $%.2f — over the $%.2f budget"
                        % (true_total, BUDGET))
    return None


# qty=150 at the true price ($10) = $1500 > $1000 budget -> the agent SHOULD decline.
TASK = {"sku": "WIDGET-9", "qty": 150}


def main():
    print("4-tool fulfillment chain:  get_stock -> get_price -> budget check -> place_order")
    print("=" * 70)
    print("Task: order 150 units. True price $10 -> true total $1500 > $1000 budget (should DECLINE).\n")
    # Corrupt the PRICE early in the chain (a stale price cache): $10 -> $2.
    res = fl.check(agent, TASK,
                   faults=[fl.WrongNumber(factor=0.2, targets=["get_price"])],
                   invariants=[within_true_budget], trials=3)
    res.report(write_md=False)
    print("\n" + "=" * 70)
    print("The cascade: a corrupted PRICE ($10->$2) made the total look like $300, the budget")
    print("check passed, and the agent approved a $1500 order — over budget, no error. The fault")
    print("was in tool #2; the wrong ACTION was three steps later. faultline followed it through.")
    return res


if __name__ == "__main__":
    res = main()
    sys.exit(0 if res.silent else 1)
