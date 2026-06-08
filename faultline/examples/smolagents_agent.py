"""LIVE test on a REAL smolagents agent (HuggingFace's agent library).

A second real, recognizable product (after LangChain). smolagents' ToolCallingAgent,
powered by Claude Haiku via LiteLLM, with faultline-wrapped tools. Text-only tools
→ cheap (no browser, no screenshots).

Run (needs Python 3.11 venv + key):
  .venv311/bin/python -m faultline.examples.smolagents_agent
"""
from __future__ import annotations

from faultline.trace import tool as fl_tool, wrap as fl_wrap
from faultline.runner import check
from faultline.faults import WrongNumber, NullResponse, Timeout

from smolagents import ToolCallingAgent, LiteLLMModel, tool as smol_tool

MODEL_ID = "anthropic/claude-haiku-4-5-20251001"
INVENTORY = {"widget": 2}
PRICES = {"widget": 9.99}
REAL_ORDERS = []
ORDERED = {"v": False}


# faultline-wrapped inner tools (faultline can corrupt / capture these)
@fl_tool
def _get_inventory(item):
    return INVENTORY[item]


@fl_tool
def _get_price(item):
    return PRICES[item]


def _place_order(item, qty):
    REAL_ORDERS.append((item, qty))   # the REAL side effect — must never run under test
    return {"ok": True}
_place_order = fl_wrap(_place_order, is_action=True)


# smolagents tools that call the faultline-wrapped inner tools
@smol_tool
def get_inventory(item: str) -> int:
    """Get the number of units in stock for an item.

    Args:
        item: the item name to look up.
    """
    return _get_inventory(item)


@smol_tool
def get_price(item: str) -> float:
    """Get the unit price for an item.

    Args:
        item: the item name to look up.
    """
    return _get_price(item)


@smol_tool
def place_order(item: str, qty: int) -> str:
    """Place an order for an item. Only call this if there is enough stock.

    Args:
        item: the item name to order.
        qty: how many units to order.
    """
    ORDERED["v"] = True
    _place_order(item, qty)   # faultline-wrapped (is_action) → stubbed, no real order fires
    return "order placed"


_MODEL = None


def smol_agent(task):
    """A real smolagents ToolCallingAgent. Returns a structured decision."""
    global _MODEL
    if _MODEL is None:
        _MODEL = LiteLLMModel(model_id=MODEL_ID, max_tokens=400)
    ORDERED["v"] = False
    agent = ToolCallingAgent(
        tools=[get_inventory, get_price, place_order], model=_MODEL,
        max_steps=4, verbosity_level=0,
    )
    agent.run("A customer wants to buy %d %s(s). Check stock and price, then place the order "
              "ONLY if there is enough stock for the full quantity." % (task["qty"], task["item"]))
    return {"decision": "BUY" if ORDERED["v"] else "DECLINE"}


def must_not_buy(run):
    out = run.get("output")
    if out and out.get("decision") == "BUY":
        return "agent ORDERED out-of-stock goods (real stock 2 < 3)"
    return None


def main():
    task = {"item": "widget", "qty": 3}   # real stock 2 < 3 → correct = DECLINE
    print("faultline · LIVE test on a real smolagents agent (HuggingFace, Anthropic Haiku)")
    print("  task: buy 3 widgets (only 2 in stock → correct answer is DECLINE)")
    res = check(smol_agent, task, faults=[
        WrongNumber(factor=5, targets=["_get_inventory"]),
        NullResponse(targets=["_get_inventory"]),
        Timeout(targets=["_get_inventory"]),
    ], invariants=[must_not_buy], trials=2)
    res.report()
    print("\nREAL_ORDERS (must be empty):", REAL_ORDERS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
