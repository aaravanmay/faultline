"""Test: fl.instrument handles real installed crewAI tools (no new adapter needed).

crewAI `BaseTool` exposes `._run` — the same seam as LangChain's BaseTool — so the universal
`fl.instrument()` already wraps it. This proves + protects that: a fault must NOT reach the tool
before instrument and DOES after, through the real `BaseTool.run()` path.

Needs Python 3.10+ with crewai (run under .venv311). Skips loudly, stays green on the 3.9 suite.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from crewai.tools import BaseTool
    from pydantic import BaseModel
    from typing import Type
except Exception as exc:  # noqa: BLE001
    print("SKIPPED — crewai not importable (needs Python 3.10+): %s" % exc)
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
    class InvInput(BaseModel):
        sku: str

    class GetInventory(BaseTool):
        name: str = "get_inventory"
        description: str = "Look up on-hand inventory for a SKU."
        args_schema: Type[BaseModel] = InvInput

        def _run(self, sku: str) -> dict:
            return {"sku": sku, "units": 240}

    return GetInventory()


def invoke(tool_obj):
    def agent(task):
        return tool_obj.run(sku="A-12")
    return agent


WN = lambda: fl.WrongNumber(targets=["get_inventory"])

t = make_tool()
before = fl.run_once(invoke(t), {}, WN())
expect("real crewai BaseTool — fault does NOT reach before instrument (fail-first)",
       before["output"].get("units") == 240)
fl.instrument([t])
after = fl.run_once(invoke(t), {}, WN())
expect("fl.instrument() wraps crewai BaseTool._run (fault reaches the real tool)",
       after["output"].get("units") != 240)

base = fl.run_once(invoke(t), {})
expect("instrumented crewai tool is transparent with no fault", base["output"].get("units") == 240)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
