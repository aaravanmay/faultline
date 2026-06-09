"""Tests for auto-instrumentation (faultline.instrument_*). Deterministic, no framework dependency.

Uses a tiny stand-in that mimics a LangChain/LlamaIndex tool's shape (.name + .func), so we test the
adapter logic without installing LangChain.  Run: python3 tests/test_adapters.py
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


class FakeLCTool:            # mimics a LangChain Tool: has .name and .func
    def __init__(self, name, func):
        self.name = name
        self.func = func


# ---- a normal tool, NO manual @fl.tool ----
def search(q):
    return "real:" + q

t = FakeLCTool("search", search)
fl.instrument_langchain([t])

def agent(task):
    return {"a": t.func(task["q"])}

base = fl.run_once(agent, {"q": "x"})
check("instrument: tool recorded by its framework name", base["events"][0]["tool"] == "search")
check("instrument: baseline returns the real value", base["output"]["a"] == "real:x")

faulted = fl.run_once(agent, {"q": "x"}, fault=fl.NullResponse(targets=["search"]))
check("instrument: fault targets the tool by framework name", faulted["output"]["a"] is None)
check("instrument: event marked faulted", faulted["events"][0]["faulted"] is True)

check("instrument: tool is normal outside a run", t.func("y") == "real:y")
check("instrument: not double-wrapped on re-instrument",
      (fl.instrument_langchain([t]) or True) and t.func("z") == "real:z")


# ---- an ACTION tool: real function must NOT fire under test ----
fired = {"n": 0}
def place_order(**kw):
    fired["n"] += 1
    return "PLACED"

ta = FakeLCTool("place_order", place_order)
fl.instrument_langchain([ta], actions=["place_order"])

def action_agent(task):
    ta.func(item="widget", qty=3)
    return {"done": True}

ra = fl.run_once(action_agent, {})
check("instrument(actions): event flagged is_action", ra["events"][0]["is_action"] is True)
check("instrument(actions): real side-effect did NOT fire under test", fired["n"] == 0)


# ---- LlamaIndex-shaped tool (.metadata.name + .fn) ----
class FakeMeta:
    def __init__(self, name): self.name = name
class FakeLITool:
    def __init__(self, name, fn): self.metadata = FakeMeta(name); self.fn = fn

li = FakeLITool("lookup", lambda k: "v:" + k)
fl.instrument_llamaindex([li])
rli = fl.run_once(lambda task: {"r": li.fn("a")}, {})
check("instrument_llamaindex: recorded by metadata.name", rli["events"][0]["tool"] == "lookup")


passed = sum(1 for _, c in results if c)
print("\n%d passed, %d failed" % (passed, len(results) - passed))
sys.exit(0 if passed == len(results) else 1)
