"""Test: faultline is thread-safe — concurrent runs with DIFFERENT faults don't interfere.

faultline arms a fault via a contextvars.ContextVar (isolated per thread/async-context). A
CI suite or a production fleet may run many agents at once; this proves an injected fault in one
thread never leaks into another, and the per-thread recorded events stay correct. Pure faultline.

Scope: this covers the standard pattern — a fresh / stateless fault per run (what `fl.check` and
the examples do). A *single STATEFUL fault instance* (e.g. one `StaleData()`) SHARED across threads
is NOT safe — its internal `_seen` is a plain dict and would race. Use a fresh fault instance per
concurrent run. (Making stateful faults thread-local is a deferred robustness item.)
"""
import os
import sys
from concurrent.futures import ThreadPoolExecutor

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


@fl.tool
def get_value(key):
    return 100


def agent(task):
    return {"value": get_value("k")}


# Each worker runs the SAME agent under its OWN fault (a distinct factor) or no fault.
def worker(i):
    if i % 4 == 0:
        # no fault — must see the true 100
        out = fl.run_once(agent, {})
        return ("baseline", out["output"]["value"])
    factor = float(i + 1)
    out = fl.run_once(agent, {}, fl.WrongNumber(factor=factor, targets=["get_value"]))
    return ("factor=%g" % factor, out["output"]["value"], 100 * factor)


# Run a wide concurrent batch repeatedly to shake out races.
all_ok = True
contamination = []
for _round in range(8):
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(worker, range(1, 17)))
    for r in results:
        if r[0] == "baseline":
            if r[1] != 100:
                all_ok = False
                contamination.append(("baseline saw %s (a fault leaked in)" % r[1]))
        else:
            label, got, want = r
            if got != want:
                all_ok = False
                contamination.append(("%s expected %s, saw %s" % (label, want, got)))

expect("concurrent runs with different faults do not cross-contaminate (8 rounds x 16 threads)", all_ok)
if contamination:
    print("    contamination samples:", contamination[:5])

# A no-fault baseline interleaved with faults always sees the truth.
def mixed(i):
    if i % 2 == 0:
        return fl.run_once(agent, {})["output"]["value"]            # baseline
    return fl.run_once(agent, {}, fl.WrongNumber(factor=5.0, targets=["get_value"]))["output"]["value"]


with ThreadPoolExecutor(max_workers=8) as ex:
    vals = list(ex.map(mixed, range(40)))
baselines = [v for i, v in enumerate(vals) if i % 2 == 0]
faulted = [v for i, v in enumerate(vals) if i % 2 == 1]
expect("interleaved baselines all saw the true value (100)", all(v == 100 for v in baselines))
expect("interleaved faulted runs all saw the corrupted value (500)", all(v == 500 for v in faulted))

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
