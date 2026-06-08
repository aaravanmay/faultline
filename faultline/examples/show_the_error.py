"""Show the agent getting caught in the act — prints the REAL tool-by-tool trace
of a smolagents agent (a) running correctly, then (b) being fed a corrupted number
by faultline and silently placing an order it should have refused.

Output is plain text (no ANSI) so it renders cleanly into a screenshot.

Run:  .venv311/bin/python -m faultline.examples.show_the_error
"""
from __future__ import annotations

from faultline.trace import run_once
from faultline.faults import WrongNumber, NullResponse, Timeout
from faultline.examples.smolagents_agent import (
    get_inventory, get_price, place_order, ORDERED, REAL_ORDERS, MODEL_ID, INVENTORY,
)

from smolagents import ToolCallingAgent, LiteLLMModel

_MODEL = LiteLLMModel(model_id=MODEL_ID, max_tokens=400)
REAL_STOCK = INVENTORY["widget"]   # 2
TASK = {"item": "widget", "qty": 3}


def agent_fn(task):
    ORDERED["v"] = False
    agent = ToolCallingAgent(
        tools=[get_inventory, get_price, place_order], model=_MODEL,
        max_steps=4, verbosity_level=0,
    )
    final = agent.run(
        "A customer wants to buy %d %s(s). Check stock and price, then place the order "
        "ONLY if there is enough stock for the full quantity. Explain your decision."
        % (task["qty"], task["item"])
    )
    return {"decision": "BUY" if ORDERED["v"] else "DECLINE", "final": str(final)}


def _short(v, n=70):
    s = repr(v)
    return s if len(s) <= n else s[:n] + "..."


def _flat(s, n=150):
    s = " ".join(str(s).split())   # collapse all whitespace/newlines
    return s if len(s) <= n else s[:n] + "..."


def show(title, fault):
    print("=" * 72)
    print(title)
    print("-" * 72)
    run = run_once(agent_fn, TASK, fault=fault)
    print("the agent's tool calls (real stock is %d; customer wants %d):" % (REAL_STOCK, TASK["qty"]))
    for ev in run["events"]:
        call = "%s(%s)" % (ev["tool"].lstrip("_"),
                           ", ".join(_short(a) for a in ev["args"]))
        if ev.get("raised"):
            print("   x  %-34s -> RAISED (tool hung / errored)%s"
                  % (call, "   <- FAULT INJECTED" if ev["faulted"] else ""))
        elif ev["is_action"]:
            print("   !  %-34s -> ACTION CAPTURED (no real order fired)" % call)
        else:
            tag = "   <- FAULT: real value was %r" % (REAL_STOCK,) if ev["faulted"] else ""
            print("   .  %-34s -> %s%s" % (call, _short(ev["result"]), tag))

    out = run["output"]
    if run["error"] is not None:
        print("\n   RESULT:  agent CRASHED -> %s: %s"
              % (type(run["error"]).__name__, run["error"]))
    else:
        verdict = "WRONG (ordered out-of-stock goods)" if out["decision"] == "BUY" else "correct (declined)"
        print("\n   agent's own words: %s" % _flat(out["final"], 150))
        print("   DECISION: %s   ->   %s" % (out["decision"], verdict))
    print()


def main():
    print("faultline -- watch a real smolagents agent get caught in the act")
    print("(only 2 widgets in stock; customer wants 3 -> the right answer is DECLINE)\n")
    show("[1] NO FAULT  --  the agent behaves correctly", None)
    show("[2] WRONG-NUMBER FAULT  --  faultline tells it 'stock = 10'", WrongNumber(factor=5, targets=["_get_inventory"]))
    show("[3] TIMEOUT FAULT  --  faultline makes the stock tool hang", Timeout(targets=["_get_inventory"]))
    print("REAL_ORDERS (must be empty -- faultline never lets a real order fire):", REAL_ORDERS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
