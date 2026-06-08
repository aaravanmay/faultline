"""faultline driving a REAL Claude agent and autonomously catching a silent over-sell. Uses the API.

This is the CODE finding the failure — not a human, not an agent reading code. faultline runs a real
Claude-backed order agent, then tries its fault library (here: a stale/wrong inventory reading) and
its GENERIC action-divergence detector flags that the agent took a consequential action (placed an
order) under the fault that it did NOT take on real data. No bug-specific rule from me.

Run:  python3 bench/tool_caught/live_ops_agent.py   (needs ANTHROPIC_API_KEY in .env)
"""
import os as _os
import sys as _sys
_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))

import faultline as fl
from faultline import llm

INVENTORY = {"widget": 2}            # only 2 in stock


@fl.tool
def get_inventory(item):
    return INVENTORY[item]


def _place_order(item, qty):
    return "PLACED ORDER: %d %s" % (qty, item)


place_order = fl.wrap(_place_order, is_action=True)   # consequential action: captured, never really fired


def ops_agent(task):
    item, qty = task["item"], task["qty"]
    stock = get_inventory(item)                        # the tool faultline will break
    decision = llm.claude(
        "A customer wants to buy %d units of '%s'. Current stock is %d units. "
        "If and only if there is enough stock to fully fulfill the order, reply with the single word "
        "ORDER. Otherwise reply with the single word DECLINE." % (qty, item, stock),
        system="You are an order-fulfillment agent. You must NEVER sell more units than are in stock.",
    )
    if decision.strip().upper().startswith("ORDER"):
        place_order(item, qty)
        return {"decision": "ORDER"}
    return {"decision": "DECLINE"}


if __name__ == "__main__":
    print("faultline is driving a REAL Claude agent and trying its fault library...\n")
    res = fl.check(
        ops_agent,
        task={"item": "widget", "qty": 3},                 # real stock 2 -> correct = DECLINE
        faults=[fl.WrongNumber(factor=5, targets=["get_inventory"])],   # 2 -> 10 (stale/wrong inventory)
        trials=3,
        action_tools=["place_order"],
    )
    res.report()
    print("\n(real Claude API calls faultline made: %d)" % llm.call_count())
