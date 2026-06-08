"""THE HUNT — point faultline at a real smolagents agent on a realistic, high-stakes
task and see if a broken tool makes it report a confidently wrong business number.

Task: "How many of our stores are unprofitable?" The real answer is 3.
Fault: Truncate — the data tool returns only HALF its rows (exactly what happens
with a forgotten pagination limit or a capped API). The agent never knows rows
are missing, so it counts what it sees and reports a wrong total as fact.

This is a realistic silent failure: read-only question, no action taken, plausible
answer, no error. It also shows a real LIMIT of the automatic catcher — for a
read-only wrong-aggregate there is no action to diverge and no value to parrot, so
you need an INVARIANT to catch it. We run with that invariant and call it out.

Run:  .venv311/bin/python -m faultline.examples.hunt_smolagents
"""
from __future__ import annotations

import re

from faultline.trace import tool as fl_tool
from faultline.runner import check
from faultline.detect import classify_trial
from faultline.trace import run_once
from faultline.faults import Truncate, NullResponse, Timeout

from smolagents import ToolCallingAgent, LiteLLMModel, tool as smol_tool

MODEL_ID = "anthropic/claude-haiku-4-5-20251001"

# our "database": 6 stores, 3 of them losing money (East, West, Harbor)
STORE_REVENUES = [("North", 100), ("East", -50), ("South", 200),
                  ("West", -30), ("Central", 80), ("Harbor", -10)]
TRUE_UNPROFITABLE = sum(1 for _, r in STORE_REVENUES if r < 0)   # = 3

_MODEL = None


@fl_tool
def _list_store_revenues():
    return list(STORE_REVENUES)


@smol_tool
def list_store_revenues() -> list:
    """List every store and its monthly revenue in dollars (negative = a loss)."""
    return _list_store_revenues()


def agent(task):
    global _MODEL
    if _MODEL is None:
        _MODEL = LiteLLMModel(model_id=MODEL_ID, max_tokens=400)
    a = ToolCallingAgent(tools=[list_store_revenues], model=_MODEL, max_steps=4, verbosity_level=0)
    final = a.run("How many of our stores are unprofitable (negative revenue)? "
                  "Use the tool, then answer with just the number.")
    nums = re.findall(r"-?\d+", str(final))
    count = int(nums[0]) if nums else None
    return {"count": count, "text": str(final)}


def must_count_all_stores(run):
    out = run.get("output") or {}
    c = out.get("count")
    if c is not None and c != TRUE_UNPROFITABLE:
        return "reported %s unprofitable stores; the real number is %s" % (c, TRUE_UNPROFITABLE)
    return None


def main():
    print("faultline THE HUNT -- a real smolagents agent (HuggingFace), realistic task")
    print("  task: 'how many stores are unprofitable?'  (true answer: %d)\n" % TRUE_UNPROFITABLE)

    task = {}
    faults = [Truncate(targets=["_list_store_revenues"]),
              NullResponse(targets=["_list_store_revenues"]),
              Timeout(targets=["_list_store_revenues"])]

    # also measure the AUTOMATIC catcher (no invariant) to show the honest limit
    baseline = run_once(agent, task)
    print("  baseline answer (no fault): %r  -> %s\n"
          % (baseline["output"].get("count"),
             "correct" if baseline["output"].get("count") == TRUE_UNPROFITABLE else "WRONG"))

    res = check(agent, task, faults, invariants=[must_count_all_stores], trials=2)
    res.report()

    # honest add-on: would the no-oracle catcher alone have caught the Truncate?
    print("\n  --- automatic catcher alone (no invariant) on the Truncate fault ---")
    trunc = run_once(agent, task, Truncate(targets=["_list_store_revenues"]))
    auto, detail = classify_trial(baseline, trunc, None, invariants=[])
    print("    agent said: %r  (truncated data hid half the stores)" % trunc["output"].get("count"))
    print("    automatic verdict: %s  (%s)" % (auto, detail))
    print("    -> read-only wrong-aggregate: no action, no parroted value, so the")
    print("       automatic catcher MISSES it. You need an invariant here. Honest limit.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
