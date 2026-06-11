"""Test: fl.doctor — preflight diagnosis (read-only, no faults injected). Pure faultline (3.9)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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


def _statuses(rep):
    return [s for _, _, s in rep.checks]


# READY: wrapped tools fire, corruptible returns
@fl.tool
def get_inv(sku):
    return {"sku": sku, "units": 240}


place = fl.wrap(lambda sku, qty: None, is_action=True, name="place_order")


def good_agent(task):
    units = get_inv(task["sku"])["units"]
    if units < 250:
        place(task["sku"], 250 - units)
    return {"ordered": max(0, 250 - units)}


rep = fl.doctor(good_agent, {"sku": "A-12"})
expect("a properly-wired agent is READY", rep.ready and "fail" not in _statuses(rep))
expect("doctor reports the wrapped tools that fired",
       any("get_inv" in d for _, d, _ in rep.checks))
expect("doctor flags the action tool as stubbed",
       any("place_order" in d and "stubbed" in l for l, d, _ in rep.checks))
expect("doctor.report() renders without error", bool(rep.report(write=False)))

# NOT READY: no wrapped tools fired (the #1 first-run failure)
def no_tools(task):
    return {"answer": 42}


r2 = fl.doctor(no_tools, {})
expect("an agent with NO wrapped tools is NOT READY", not r2.ready)
expect("doctor explains the no-tools failure actionably",
       any("Wrap your tool calls" in d for _, d, _ in r2.checks))

# WARN: a tool returning an uncorruptible type is a coverage gap (not a hard fail)
@fl.tool
def stream_tool(k):
    return (x for x in [1, 2, 3])


def gen_agent(task):
    list(stream_tool("k"))
    return {"ok": 1}


r3 = fl.doctor(gen_agent, {})
expect("a generator-returning tool is flagged as a coverage-gap WARN", "warn" in _statuses(r3))
expect("an agent that still has a corruptible tool can be READY despite a warn", r3.ready)  # gen tool only -> warn, no fail

# async agent -> NOT READY, with the sync-shim workaround surfaced
async def async_agent(task):
    return {}


r4 = fl.doctor(async_agent, {})
expect("an async agent is NOT READY", not r4.ready)
expect("doctor surfaces the async workaround (sync shim)",
       any("sync shim" in d or "async" in d.lower() for _, d, _ in r4.checks))

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
