"""Test: fl.instrument_pydantic_ai / fl.instrument against the REAL installed pydantic-ai.

Fail-first: the fault must NOT reach the tool before instrument, and DOES after — through the
real pydantic-ai Tool's callable seam (`.function`). Needs Python 3.10+ with pydantic-ai
(run under .venv311). Skips loudly and stays green under the 3.9 suite.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from pydantic_ai.tools import Tool
except Exception as exc:  # noqa: BLE001
    print("SKIPPED — pydantic-ai not importable (needs Python 3.10+): %s" % exc)
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
    return Tool(get_inventory)


def invoke_agent(tool_obj):
    def agent(task):
        return tool_obj.function(sku="A-12")
    return agent


WN = lambda: fl.WrongNumber(targets=["get_inventory"])

# fail-first on the real pydantic-ai Tool.function seam
t = make_tool()
before = fl.run_once(invoke_agent(t), {}, WN())
expect("real pydantic-ai Tool — fault does NOT reach before instrument (fail-first)",
       before["output"].get("units") == 240)
fl.instrument_pydantic_ai([t])
after = fl.run_once(invoke_agent(t), {}, WN())
expect("real pydantic-ai Tool — fault reaches it after instrument_pydantic_ai",
       after["output"].get("units") != 240)

# universal fl.instrument() also handles it
t2 = make_tool()
fl.instrument([t2])
u = fl.run_once(invoke_agent(t2), {}, WN())
expect("fl.instrument() (universal) wraps a real pydantic-ai tool", u["output"].get("units") != 240)

# transparent with no fault active
base = fl.run_once(invoke_agent(t2), {})
expect("instrumented pydantic-ai tool is transparent with no fault", base["output"].get("units") == 240)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
