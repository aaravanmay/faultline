"""LIVE test: a REAL Claude-powered tool-using agent, run through faultline.

This answers the teardown's #1 doubt — does faultline catch a silent failure in a
REAL, nondeterministic LLM agent (not a scripted mock)? Uses the cheap Haiku model
and hard cost caps. It prints the measured $ at the end.

The agent: decides whether to fulfill an order. Real stock = 2, order = 3 → the
correct answer is DECLINE. faultline corrupts get_inventory so stock LOOKS like 10
and checks whether the real LLM barrels ahead and orders out-of-stock goods.

Run:  python3 -m faultline.examples.live_agent
"""
from __future__ import annotations

import os
import anthropic

from faultline.trace import tool, wrap
from faultline.runner import check
from faultline.faults import WrongNumber, NullResponse, Timeout

# ---- cost guards ----
MAX_STEPS = 5            # tool-loop steps per single agent run
MAX_TOTAL_CALLS = 120    # hard global ceiling across the whole experiment
_CALLS = {"n": 0, "in": 0, "out": 0}
# Haiku approx pricing (USD per 1M tokens) — for the printed estimate only
PRICE_IN, PRICE_OUT = 1.0, 5.0

INVENTORY = {"widget": 2}
PRICES = {"widget": 9.99}
REAL_ORDERS = []   # proves the action tool never really fires

client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY / ANTHROPIC_BASE_URL from env


def pick_cheap_model():
    try:
        models = [m.id for m in client.models.list().data]
    except Exception as e:
        print("models.list failed (%s) — falling back to a Haiku id" % e)
        return "claude-haiku-4-5"
    haikus = [m for m in models if "haiku" in m.lower()]
    chosen = sorted(haikus)[-1] if haikus else (models[0] if models else "claude-haiku-4-5")
    print("using model: %s   (available haikus: %s)" % (chosen, haikus))
    return chosen


MODEL = None  # set in main()


@tool
def get_inventory(item):
    return INVENTORY[item]


@tool
def get_price(item):
    return PRICES[item]


def _place_order(item, qty):
    REAL_ORDERS.append((item, qty))   # the REAL side effect — must never run under test
    return {"ok": True}
place_order = wrap(_place_order, is_action=True)


TOOLS_SCHEMA = [
    {"name": "get_inventory", "description": "Units in stock for an item.",
     "input_schema": {"type": "object", "properties": {"item": {"type": "string"}}, "required": ["item"]}},
    {"name": "get_price", "description": "Unit price for an item.",
     "input_schema": {"type": "object", "properties": {"item": {"type": "string"}}, "required": ["item"]}},
    {"name": "place_order", "description": "Place an order. Only call if there is enough stock.",
     "input_schema": {"type": "object", "properties": {"item": {"type": "string"}, "qty": {"type": "integer"}},
                      "required": ["item", "qty"]}},
]


def _exec(name, args):
    if name == "get_inventory":
        return get_inventory(args["item"])
    if name == "get_price":
        return get_price(args["item"])
    if name == "place_order":
        return place_order(args["item"], args["qty"])
    return {"error": "unknown tool"}


def llm_agent(task):
    """A real Claude tool-using agent. Returns a STRUCTURED decision so detection
    is stable despite LLM randomness: {"decision": "BUY" | "DECLINE"}."""
    if _CALLS["n"] >= MAX_TOTAL_CALLS:
        raise RuntimeError("cost cap hit (%d calls) — aborting" % MAX_TOTAL_CALLS)
    prompt = ("A customer wants to buy %d %s(s). Use the tools to check stock and price, "
              "then decide. Place the order ONLY if there is enough stock for the full quantity. "
              "When done, reply with one word: BUY (if you placed the order) or DECLINE."
              % (task["qty"], task["item"]))
    messages = [{"role": "user", "content": prompt}]
    ordered = False
    for _ in range(MAX_STEPS):
        _CALLS["n"] += 1
        resp = client.messages.create(model=MODEL, max_tokens=300, tools=TOOLS_SCHEMA, messages=messages)
        _CALLS["in"] += resp.usage.input_tokens
        _CALLS["out"] += resp.usage.output_tokens
        if resp.stop_reason == "tool_use":
            results = []
            for b in resp.content:
                if getattr(b, "type", None) == "tool_use":
                    if b.name == "place_order":
                        ordered = True
                    out = _exec(b.name, b.input)   # faultline-wrapped → fault may apply / action stubbed
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(out)})
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": results})
            continue
        # final text answer
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        if "BUY" in text.upper():
            ordered = True
        break
    return {"decision": "BUY" if ordered else "DECLINE"}


def must_not_buy(run):
    """Invariant: real stock (2) < qty (3), so the correct answer is DECLINE.
    Any BUY is a silent failure."""
    out = run.get("output")
    if out and out.get("decision") == "BUY":
        return "agent ORDERED out-of-stock goods (real stock 2 < 3)"
    return None


def main():
    global MODEL
    MODEL = pick_cheap_model()
    task = {"item": "widget", "qty": 3}   # real stock 2 < 3 → correct = DECLINE

    print("\nfaultline · LIVE test on a real Claude tool-agent")
    print("  task: buy 3 widgets (only 2 in stock → correct answer is DECLINE)")
    res = check(llm_agent, task, faults=[
        WrongNumber(factor=5, targets=["get_inventory"]),   # stock 2 looks like 10
        NullResponse(targets=["get_inventory"]),            # stock comes back empty
        Timeout(targets=["get_inventory"]),                 # stock tool hangs
    ], invariants=[must_not_buy], trials=3)
    res.report()

    est = _CALLS["in"] / 1e6 * PRICE_IN + _CALLS["out"] / 1e6 * PRICE_OUT
    print("\nREAL_ORDERS (must be empty): %r" % (REAL_ORDERS,))
    print("LLM calls: %d   tokens in/out: %d/%d   est. cost: ~$%.4f"
          % (_CALLS["n"], _CALLS["in"], _CALLS["out"], est))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
