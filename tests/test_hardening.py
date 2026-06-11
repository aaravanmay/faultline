"""Test: hardening fixes from the adversarial QA pass (locks them against regression).

Covers: minority-SILENT must gate (assert_resilient/scan), substring abstain false-negative,
namedtuple EmptyResult crash, and replay transform not corrupting the recording. Pure faultline.
"""
import os
import sys
from collections import namedtuple

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


# ── #1: an intermittent (minority-trial) silent failure must still gate ───
_bal = {"v": 1000}
_n = {"i": 0}


@fl.tool
def get_balance(acct):
    return _bal["v"]


def minority_silent_agent(task):
    bal = get_balance("a")
    _n["i"] += 1
    # parrots the corrupted balance ~1 in 3 calls -> a SILENT trial within trials=5
    return {"answer": "Your balance is %d" % bal} if _n["i"] % 3 == 0 else {"answer": "ok"}


res = fl.check(minority_silent_agent, {}, faults=[fl.WrongNumber(targets=["get_balance"])],
               invariants=[], trials=5)
expect("aggregate verdict is INCONCLUSIVE (the gap that hid the bug)",
       res.rows[0]["verdict"] == "INCONCLUSIVE" and "SILENT" in res.rows[0]["trials"])
_n["i"] = 0
raised = False
try:
    fl.assert_resilient(minority_silent_agent, {},
                        faults=[fl.WrongNumber(targets=["get_balance"])], trials=5)
except AssertionError:
    raised = True
expect("assert_resilient RAISES on an intermittent silent failure", raised)

# ── #4: abstain markers must not false-match as substrings (fabrication FN) ─
@fl.tool
def search(q):
    return ["doc"]


inv = fl.tools_really_called(["search"])


def fab_na(task):
    return "See /n/applications for details: revenue grew 40%."     # 'n/a' as a substring


def fab_emptyset(task):
    return "The emptyset theorem confirms 12 nodes."                # 'empty' as a substring


def honest_abstention(task):
    return "I could not find any results for that."                 # a real abstention


expect("fabrication with 'n/a' substring is CAUGHT (not read as abstention)",
       inv(fl.run_once(fab_na, {})) is not None)
expect("fabrication with 'empty' substring is CAUGHT",
       inv(fl.run_once(fab_emptyset, {})) is not None)
expect("a genuine abstention is still SILENT (no false positive)",
       inv(fl.run_once(honest_abstention, {})) is None)

# ── #5: EmptyResult must not crash a namedtuple-returning tool ─────────────
Inv = namedtuple("Inv", ["sku", "units"])


@fl.tool
def get_inv(sku):
    return Inv(sku=sku, units=240)


def nt_agent(task):
    return {"units": get_inv("A").units}


r = fl.run_once(nt_agent, {}, fl.EmptyResult(targets=["get_inv"]))
expect("EmptyResult leaves a namedtuple unchanged (no wrong-shape crash)", r["error"] is None)

# ── replay: a mutating transform must not corrupt the recording ────────────
def ctx_agent(task):
    return {"decision": "detailed" if len(task.get("context", "")) >= 20 else "brief"}


rec = fl.record(ctx_agent, {"context": "x" * 50})


def mutating_transform(t):
    t["context"] = t["context"][:5]   # mutates in place — must NOT touch the recording
    return t


r1 = fl.replay(ctx_agent, rec, watch=lambda o: {"decision": o["decision"]}, transform=mutating_transform)
r2 = fl.replay(ctx_agent, rec, watch=lambda o: {"decision": o["decision"]}, transform=mutating_transform)
expect("recording survives a mutating transform (deterministic across replays)",
       r1.regressed() == r2.regressed() == True)
expect("the recording's task was not corrupted by the transform",
       len(rec["task"]["context"]) == 50)

# ── FN fix: a corrupted financial figure shown with thousands-separators is caught ─
@fl.tool
def get_balance(acct):
    return {"acct": acct, "balance": 1200}


def currency_agent(task):
    bal = get_balance(task)["balance"]
    return {"msg": "Account balance: ${:,}".format(bal)}   # 1200->"$1,200"; 6000->"$6,000"


cres = fl.check(currency_agent, {}, faults=[fl.WrongNumber(factor=5.0, targets=["get_balance"])],
                invariants=[], trials=3)
expect("corrupted $6,000-style figure is CAUGHT (thousands-separator FN fixed)",
       cres.rows[0]["verdict"] == "FAIL")

# guard: the thousands-strip must not FALSE-POSITIVE a correct agent whose output happens to
# contain a comma'd number that did NOT come from corruption (a fixed label).
@fl.tool
def get_count(q):
    return 7


def safe_label_agent(task):
    get_count("x")
    return {"report": "Processed 1,000 records successfully."}   # fixed label, not corrupted


sres = fl.check(safe_label_agent, {}, faults=[fl.WrongNumber(factor=5.0, targets=["get_count"])],
                invariants=[], trials=3)
expect("thousands-strip does not false-positive a fixed comma'd label",
       sres.rows[0]["verdict"] == "PASS")

# ── F5: scenarios must not crash on a truthy non-string invariant return ───
def _ok_agent(task):
    return {"x": 1}


sc = fl.scenarios(_ok_agent, [("c", {})], [lambda run: ["not", "a", "string"]])
expect("scenarios coerces a non-string invariant message (no crash)", sc.rows[0]["status"] == "UNSAFE")

# ── F4: a CRASH must not be summarized with the green 'all held' line ───────
def _crasher(task):
    raise RuntimeError("boom")


sc_rep = fl.scenarios(_crasher, [("c", {})], [lambda run: None]).report(write=False)
expect("scenarios report does NOT print the green line when a case crashed",
       "held the rule on every" not in sc_rep and "CRASHED" in sc_rep)

pr_rep = fl.probe(lambda inp: (_ for _ in ()).throw(RuntimeError("boom")),
                  [("c1", 5)], [lambda inp, out, err: None]).report(write=False)
expect("probe report does NOT print the green line when a case crashed",
       "held across every probed" not in pr_rep and "CRASHED" in pr_rep)

# ── async agent must fail LOUD (clear error + workaround), not silently return a coroutine ──
async def _async_agent(task):
    return {"v": 1}


_ar = fl.run_once(_async_agent, {})
expect("async agent fails loud (clear error), not a silent coroutine output",
       _ar["error"] is not None and "sync shim" in str(_ar["error"]) and _ar["output"] is None)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
