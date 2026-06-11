"""Test: fl.instrument_langchain / fl.instrument against the REAL installed langchain.

The existing adapters test uses a hand-rolled tool shape; this one proves the
adapter is non-vacuous on a real langchain `StructuredTool` (the actual object
LangChain agents execute). Fail-first: the fault must NOT reach the tool before
instrument, and DOES after — through the real `.invoke()` path.

Needs Python 3.10+ with langchain-core installed (run under .venv311). Skips
loudly and stays green under the 3.9 suite.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    from langchain_core.tools import tool as lc_tool
except Exception as exc:  # noqa: BLE001
    print("SKIPPED — langchain_core not importable (needs Python 3.10+): %s" % exc)
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
    @lc_tool
    def get_price(ticker: str) -> dict:
        """Look up a ticker's price."""
        return {"ticker": ticker, "price": 100}
    return get_price


def invoke_agent(tool_obj):
    def agent(task):
        return tool_obj.invoke({"ticker": "NVDA"})
    return agent


WN = lambda: fl.WrongNumber(targets=["get_price"])

# ── instrument_langchain on a real StructuredTool (fail-first) ─────────────
t = make_tool()
before = fl.run_once(invoke_agent(t), {}, WN())
expect("real langchain tool — fault does NOT reach before instrument (fail-first)",
       before["output"].get("price") == 100)
fl.instrument_langchain([t])
after = fl.run_once(invoke_agent(t), {}, WN())
expect("real langchain tool — fault reaches it after instrument_langchain",
       after["output"].get("price") != 100)

# ── the universal fl.instrument() one-liner on a real tool ────────────────
t2 = make_tool()
fl.instrument([t2])
u = fl.run_once(invoke_agent(t2), {}, WN())
expect("fl.instrument() (universal) wraps a real langchain tool", u["output"].get("price") != 100)

# ── idempotent: a second instrument call doesn't double-wrap / break it ────
fl.instrument([t2])
u2 = fl.run_once(invoke_agent(t2), {}, WN())
expect("instrument is idempotent (no double-wrap breakage)", u2["output"].get("price") != 100)
base2 = fl.run_once(invoke_agent(t2), {})   # no fault -> transparent
expect("instrumented tool is transparent with no fault active", base2["output"].get("price") == 100)

# ── actions: a real side-effecting tool's function must NOT fire under test ─
fired = {"n": 0}


@lc_tool
def place_order(ticker: str, qty: int) -> dict:
    """Place an order (real side effect)."""
    fired["n"] += 1
    return {"status": "ok"}


fl.instrument_langchain([place_order], actions=["place_order"])


def order_agent(task):
    return place_order.invoke({"ticker": "NVDA", "qty": 5})


fl.run_once(order_agent, {}, fl.WrongNumber(targets=["place_order"]))
expect("action tool's real function did NOT fire under test (stubbed)", fired["n"] == 0)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
