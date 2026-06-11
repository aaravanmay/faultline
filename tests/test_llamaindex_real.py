"""Test: fl.instrument_llamaindex / fl.instrument against the REAL installed llama-index.

Fail-first: the fault must NOT reach the tool before instrument, and DOES after —
through the real FunctionTool.call() path. (The adapter wraps `_fn`; this proves
that's the attribute call() actually invokes on the installed version.)

Needs Python 3.10+ with llama-index-core (run under .venv311). Skips loudly and
stays green under the 3.9 suite.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from llama_index.core.tools import FunctionTool
except Exception as exc:  # noqa: BLE001
    print("SKIPPED — llama-index-core not importable (needs Python 3.10+): %s" % exc)
    print("0 passed, 0 failed")
    sys.exit(0)

import faultline as fl

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
    def get_inventory(sku: str) -> dict:
        """Look up inventory for a SKU."""
        return {"sku": sku, "units": 240}
    return FunctionTool.from_defaults(fn=get_inventory)


def invoke_agent(tool_obj):
    def agent(task):
        out = tool_obj.call(sku="A-12")
        return out.raw_output if hasattr(out, "raw_output") else out
    return agent


WN = lambda: fl.WrongNumber(targets=["get_inventory"])

# fail-first on the real FunctionTool.call() path
t = make_tool()
before = fl.run_once(invoke_agent(t), {}, WN())
expect("real FunctionTool — fault does NOT reach before instrument (fail-first)",
       before["output"].get("units") == 240)
fl.instrument_llamaindex([t])
after = fl.run_once(invoke_agent(t), {}, WN())
expect("real FunctionTool — fault reaches it after instrument_llamaindex",
       after["output"].get("units") != 240)

# universal fl.instrument() also handles it
t2 = make_tool()
fl.instrument([t2])
u = fl.run_once(invoke_agent(t2), {}, WN())
expect("fl.instrument() (universal) wraps a real LlamaIndex tool", u["output"].get("units") != 240)

# transparent with no fault active
base = fl.run_once(invoke_agent(t2), {})
expect("instrumented LlamaIndex tool is transparent with no fault", base["output"].get("units") == 240)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
