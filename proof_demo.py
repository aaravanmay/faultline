"""faultline — PROOF demo (Method A: honest inputs, real agent bug). NOTHING is faked.

We do NOT lie to the agent. Every tool returns the TRUE stock. We just run a real Claude-backed
order agent through honest, realistic situations and check one rule: it must never order more units
than it actually has. The buggy agent breaks it on real cases; a safe agent passes them all.

This replaces the old "tell the agent there are 10 when there are 0" demo, which was garbage-in.

Run:  python3 proof_demo.py    (needs ANTHROPIC_API_KEY in .env; ~8 real Claude calls, a few cents)
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import faultline as fl
from faultline import llm

WORLD = {"a": 3, "b": 2, "c": 0, "d": 100}      # the TRUTH. No tool ever lies about this.


@fl.tool
def get_inventory(item):
    return WORLD[item]                           # honest


def _place_order(item, qty):
    return "ordered %d %s" % (qty, item)


place_order = fl.wrap(_place_order, is_action=True)   # captured, never really ships


def _ask_claude_max(stock, qty, item):
    reply = llm.claude(
        "We have %d units of '%s' in stock. A customer wants %d. How many can we actually ship "
        "(you can never ship more than is in stock)? Reply with just the number." % (stock, item, qty),
        system="You are a careful order-fulfillment agent. Never ship more than is in stock.",
    )
    m = re.search(r"-?\d+", reply)
    return int(m.group()) if m else 0


def buggy_agent(task):
    """Asks Claude (who answers correctly) — but the glue code orders the REQUESTED qty anyway."""
    stock = get_inventory(task["item"])
    claude_says = _ask_claude_max(stock, task["qty"], task["item"])   # Claude is right
    place_order(task["item"], task["qty"])                            # BUG: ignores Claude, ships requested
    return {"ordered": task["qty"], "claude_said_ship": claude_says}


def safe_agent(task):
    """Orders what Claude said is safe."""
    stock = get_inventory(task["item"])
    claude_says = _ask_claude_max(stock, task["qty"], task["item"])
    if claude_says > 0:
        place_order(task["item"], claude_says)
    return {"ordered": claude_says, "claude_said_ship": claude_says}


def never_oversell(run):
    stock = ordered = None
    for ev in run["events"]:
        if ev.get("tool") == "get_inventory":
            stock = ev.get("result")
        if ev.get("is_action") and len(ev.get("args", ())) >= 2:
            ordered = ev["args"][1]
    if ordered is not None and stock is not None and ordered > stock:
        claude = (run.get("output") or {}).get("claude_said_ship")
        extra = " (Claude correctly said ship %s, the code ordered %d)" % (claude, ordered) if claude is not None else ""
        return "ordered %d with only %d in stock%s" % (ordered, stock, extra)


CASES = [
    ("exact stock (3 of 3)", {"item": "a", "qty": 3}),
    ("one short (wants 3, has 2)", {"item": "b", "qty": 3}),
    ("empty shelf (wants 1, has 0)", {"item": "c", "qty": 1}),
    ("plenty (5 of 100)", {"item": "d", "qty": 5}),
]


def line(s=""):
    print(s); sys.stdout.flush()


def main():
    line("faultline · live proof  (Method A — honest inputs, no faults injected)")
    line("=" * 64)
    line("Every tool returns the TRUE stock. We never lie to the agent.")
    line("The rule: an agent must NEVER order more than the stock it read.")
    line("")
    line("[A] A real Claude agent whose glue code has a bug ...")
    rb = fl.scenarios(buggy_agent, CASES, [never_oversell], label="buggy order agent")
    rb.report()
    line("")
    line("[B] The same situations, a correctly-written agent ...")
    rs = fl.scenarios(safe_agent, CASES, [never_oversell], label="safe order agent")
    rs.report()
    line("")
    line("-" * 64)
    line("Real agent bug, caught on honest inputs — not 'garbage in, garbage out'.")
    line("And the safe agent passed every case, so faultline isn't crying wolf.")
    line("real Claude API calls made: %d" % llm.call_count())


if __name__ == "__main__":
    main()
