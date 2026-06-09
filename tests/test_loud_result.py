"""The most important guarantee faultline can make: a result is NEVER a quiet false green.

Locks in the first-user feedback fix — every result type must loudly report failure,
and a broken/malformed property must not read as a pass.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import faultline as fl

results = []
def check(name, cond):
    results.append((name, cond))
    print(("  ok  " if cond else "FAIL  ") + name)


# --- a result with a real break must scream FAIL on every accessor -----------
def fn_bad(d):
    return {"out": "bad"}
def always_break(inp, out, err):
    return "rule broken"

r = fl.fuzz(fn_bad, {"x": 1}, [always_break])
check("break: .ok is False",            r.ok is False)
check("break: .passed is False",        r.passed is False)
check("break: .failed is True",         r.failed is True)
check("break: len(r) > 0",              len(r) > 0)
check("break: bool(r) is True",         bool(r) is True)
check("break: .breaks non-empty",       len(r.breaks) > 0)
check("break: .failures non-empty",     len(r.failures) > 0)
check("break: 'FAIL' in repr",          "FAIL" in repr(r))
raised = False
try:
    r.assert_ok()
except AssertionError:
    raised = True
check("break: assert_ok() raises",      raised)


# --- a genuinely clean result must read as ok (no false RED either) ----------
def fn_ok(d):
    return {"out": "fine"}
def never_break(inp, out, err):
    return None

g = fl.fuzz(fn_ok, {"x": 1}, [never_break])
check("clean: .ok is True",             g.ok is True)
check("clean: .failed is False",        g.failed is False)
check("clean: len(g) == 0",             len(g) == 0)
check("clean: bool(g) is False",        bool(g) is False)
check("clean: assert_ok() returns self", g.assert_ok() is g)
check("clean: 'OK' in repr",            "OK" in repr(g))


# --- a MALFORMED property must NOT silently pass (the false-green trap) -------
def buggy_property(inp, out):          # wrong arity + will KeyError
    return inp["nope"]

b = fl.fuzz(fn_ok, {"x": 1}, [buggy_property])
check("bad-prop: not a false green (.ok False)", b.ok is False)
check("bad-prop: surfaced as PROPERTY ERROR",
      any("PROPERTY ERROR" in (row.get("detail") or "") for row in b.breaks))


# --- every result type exposes the loud API consistently ---------------------
for nm, obj in [
    ("fuzz", fl.fuzz(fn_ok, {"x": 1}, [never_break])),
    ("probe", fl.probe(fn_ok, [("base", {"x": 1})], [never_break])),
]:
    check("api: %s has .ok/.failed/.assert_ok/len" % nm,
          all(hasattr(obj, a) for a in ("ok", "failed", "breaks", "assert_ok")) and isinstance(len(obj), int))


passed = sum(1 for _, c in results if c)
failed = len(results) - passed
print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
