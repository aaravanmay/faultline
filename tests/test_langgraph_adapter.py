"""Test: fl.instrument_langgraph against the REAL installed langgraph.

Fail-first / non-vacuous discipline: for both a ToolNode and a compiled
create_react_agent graph, prove the fault does NOT reach the tool BEFORE
instrumenting, and DOES reach it AFTER. A wrap that doesn't actually intercept
the seam would fail the "after" assertion — no vacuous green.

Needs Python 3.10+ with langgraph installed (run under .venv311). Under the
3.9 suite it skips loudly and stays green (it is verified separately on 3.11).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from langchain_core.tools import tool as lc_tool
    from langgraph.prebuilt import ToolNode, create_react_agent
except Exception as exc:  # noqa: BLE001
    print("SKIPPED — langgraph/langchain_core not importable (needs Python 3.10+): %s" % exc)
    print("0 passed, 0 failed")
    sys.exit(0)

import faultline as fl
from faultline.adapters import _extract_langgraph_tools

passed = 0
failed = 0


def expect(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS %s" % name)
    else:
        failed += 1
        print("  FAIL %s" % name)


def make_tool():
    @lc_tool
    def get_inventory(sku: str) -> dict:
        """Look up inventory for a SKU."""
        return {"sku": sku, "units": 240}
    return get_inventory


def invoke_agent(tool_obj):
    """An 'agent' that invokes a specific tool object — the same callable the
    LLM-driven graph would invoke when the model calls that tool."""
    def agent(task):
        return tool_obj.invoke({"sku": "A-12"})
    return agent


WN = lambda: fl.WrongNumber(targets=["get_inventory"])

# ── 1. ToolNode path ──────────────────────────────────────────────────────
node = ToolNode([make_tool()])
tool_in_node = _extract_langgraph_tools(node)[0]
before = fl.run_once(invoke_agent(tool_in_node), {}, WN())
expect("ToolNode — fault does NOT reach the tool before instrument (fail-first)",
       before["output"].get("units") == 240)
names = fl.instrument_langgraph(node)
expect("instrument_langgraph(ToolNode) returns the tool name", "get_inventory" in names)
after = fl.run_once(invoke_agent(tool_in_node), {}, WN())
expect("ToolNode — fault NOW reaches the tool after instrument",
       after["output"].get("units") != 240)

# ── 2. compiled create_react_agent path (constructs without an LLM call) ──
graph = create_react_agent("anthropic:claude-haiku-4-5-20251001", [make_tool()])
gtool = _extract_langgraph_tools(graph)[0]
gbefore = fl.run_once(invoke_agent(gtool), {}, WN())
expect("compiled graph — fault does NOT reach before instrument (fail-first)",
       gbefore["output"].get("units") == 240)
gnames = fl.instrument_langgraph(graph)
expect("instrument_langgraph(compiled graph) finds the tool", "get_inventory" in gnames)
gtool2 = _extract_langgraph_tools(graph)[0]
gafter = fl.run_once(invoke_agent(gtool2), {}, WN())
expect("compiled graph — fault NOW reaches the tool through the graph",
       gafter["output"].get("units") != 240)

# ── 3. plain tool list path ───────────────────────────────────────────────
tools = [make_tool()]
lnames = fl.instrument_langgraph(tools)
expect("instrument_langgraph(list) wraps the tool", "get_inventory" in lnames)
lafter = fl.run_once(invoke_agent(tools[0]), {}, WN())
expect("list — fault reaches the wrapped tool", lafter["output"].get("units") != 240)

# ── 4. end-to-end: a REAL create_react_agent caught silently mis-acting ───
import contextlib
import io

from faultline.examples.langgraph_catch import run as run_catch

with contextlib.redirect_stdout(io.StringIO()):   # keep the report out of test output
    res = run_catch()
e2e_bad = [r for r in res.rows if r["verdict"] in ("FAIL", "CRASH")]
expect("end-to-end: catches a real create_react_agent acting on corrupted tool data",
       len(e2e_bad) >= 1)
expect("the catch is a SILENT failure (the dangerous kind, not just a crash)",
       any(r["verdict"] == "FAIL" for r in res.rows))
# determinism: the same scan reproduces the same verdicts
with contextlib.redirect_stdout(io.StringIO()):
    res2 = run_catch()
expect("the catch is deterministic (verdicts identical across runs)",
       [r["verdict"] for r in res.rows] == [r["verdict"] for r in res2.rows])

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
