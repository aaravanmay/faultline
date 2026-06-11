"""Test: declarative faultline.json config loading (allowlist faults, module-ref agent/invariants)."""
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import faultline as fl
from faultline.config import _build_fault, load_config_suite

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


# _build_fault from the allowlist
f = _build_fault({"type": "WrongNumber", "factor": 3, "targets": ["x"]})
expect("builds WrongNumber from a spec (with kwargs)", isinstance(f, fl.WrongNumber) and f.factor == 3)
expect("builds a fault from a bare string", isinstance(_build_fault("EmptyResult"), fl.EmptyResult))
try:
    _build_fault("NopeFault")
    expect("rejects an unknown fault type (allowlist, no eval)", False)
except ValueError:
    expect("rejects an unknown fault type (allowlist, no eval)", True)

# full round-trip
tmp = tempfile.mkdtemp()
try:
    agent_py = os.path.join(tmp, "a.py")
    with open(agent_py, "w") as fh:
        fh.write("import faultline as fl\n"
                 "@fl.tool\n"
                 "def get(s): return {'v': 10}\n"
                 "def agent(t): return {'v': get('x')['v']}\n"
                 "def rule(run): return None\n")
    cfg = os.path.join(tmp, "c.json")
    json.dump({"agent": agent_py + ":agent", "task": {},
               "faults": [{"type": "WrongNumber", "targets": ["get"]}, "EmptyResult"],
               "invariants": [agent_py + ":rule"], "trials": 2}, open(cfg, "w"))
    suite = load_config_suite(cfg)
    expect("config loads the agent callable", callable(suite["agent"]))
    expect("config builds the faults list", len(suite["faults"]) == 2)
    expect("config loads invariants as callables", len(suite["invariants"]) == 1 and callable(suite["invariants"][0]))
    expect("config carries trials", suite["trials"] == 2)
    res = fl.check(suite["agent"], suite["task"], faults=suite["faults"],
                   invariants=suite["invariants"], trials=suite["trials"])
    expect("the config-loaded suite actually runs check()", len(res.rows) == 2)

    # a config missing the agent fails cleanly
    bad = os.path.join(tmp, "bad.json")
    json.dump({"faults": ["Timeout"]}, open(bad, "w"))
    try:
        load_config_suite(bad)
        expect("a config with no agent fails cleanly", False)
    except ValueError:
        expect("a config with no agent fails cleanly", True)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
