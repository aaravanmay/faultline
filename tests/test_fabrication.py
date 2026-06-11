"""Test: tools_really_called (fabrication detector) + EmptyResult fault.

Fail-first / both-directions discipline (per the Director's FP warning):
the fabrication detector must FIRE on a confident answer with no real tool call,
and stay SILENT when the tool was really called, when the agent honestly
abstains, and when it crashed. EmptyResult must actually reach the seam and be
distinct from NullResponse (None). Pure faultline — runs on Python 3.9.
"""
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


# ── the fabrication detector: tools_really_called ─────────────────────────
@fl.tool
def search(q):
    return ["doc about %s" % q]


inv = fl.tools_really_called(["search"])

# A) FABRICATING: confident answer, never actually calls search
def fabricating_agent(task):
    return "The capital of France is Paris, according to my search."

run_fab = fl.run_once(fabricating_agent, {})
expect("FIRES on a confident answer produced without a real tool call",
       inv(run_fab) is not None)

# B) REAL-CALLING: actually calls search
def real_agent(task):
    docs = search(task["q"])
    return "Found: %s" % docs[0]

run_real = fl.run_once(real_agent, {"q": "paris"})
expect("SILENT when the tool was really called", inv(run_real) is None)

# C) HONEST ABSTENTION: didn't call, but says so (the false-positive direction)
def abstaining_agent(task):
    return "I couldn't find any results for that."

run_abs = fl.run_once(abstaining_agent, {})
expect("SILENT on honest abstention (no false positive)", inv(run_abs) is None)

# D) CRASH: a separate loud failure, not fabrication
def crash_agent(task):
    raise ValueError("boom")

run_crash = fl.run_once(crash_agent, {})
expect("SILENT on a crash (loud failure, not fabrication)", inv(run_crash) is None)

# E) end-to-end through check(): a realistic fabrication — the agent DOES call one
# tool (so a fault reaches and the trial is classified) but fabricates another it
# never called. The invariant fires on the faulted trial.
@fl.tool
def get_context(x):
    return {"ctx": "stuff", "score": 5}    # a number, so the WrongNumber fault reaches

def partial_fabricator(task):
    get_context("x")                       # really runs this
    return "The answer is Paris, per my search results."   # claims a search it never ran

res = fl.check(partial_fabricator, {},
               faults=[fl.WrongNumber(targets=["get_context"])],
               invariants=[fl.tools_really_called(["search"])], trials=2)
expect("check() flags a partial fabricator (calls one tool, fakes another)",
       any(r["verdict"] == "FAIL" for r in res.rows))

# ── EmptyResult fault: reaches the seam + distinct from None ───────────────
@fl.tool
def get_rows(region):
    return [1, 2, 3]      # real data: 3 rows


def sum_agent(task):
    rows = get_rows("west")
    return {"total": sum(rows), "n": len(rows)}


base = fl.run_once(sum_agent, {})
empty = fl.run_once(sum_agent, {}, fl.EmptyResult(targets=["get_rows"]))
expect("EmptyResult reaches the seam (agent saw [] not [1,2,3])",
       base["output"]["n"] == 3 and empty["output"]["n"] == 0)
expect("EmptyResult is empty-of-type, not None (no crash, total=0)",
       empty["error"] is None and empty["output"]["total"] == 0)

# EmptyResult is distinct from NullResponse: None would crash sum_agent (len(None))
nullr = fl.run_once(sum_agent, {}, fl.NullResponse(targets=["get_rows"]))
expect("NullResponse (None) is genuinely different from EmptyResult ([])",
       nullr["error"] is not None)

# F) the abstain-marker caveat (the FP the Director found): a prose abstention the
#    default markers don't cover trips the detector, and is silenced once supplied.
def prose_abstainer(task):
    return "Nothing to report on that topic."

run_prose = fl.run_once(prose_abstainer, {})
expect("default markers DO flag an uncovered prose abstention (documented FP)",
       fl.tools_really_called(["search"])(run_prose) is not None)
inv_custom = fl.tools_really_called(
    ["search"], abstain_markers=fl.DEFAULT_ABSTAIN_MARKERS + ("nothing to report",))
expect("silent once the agent's own abstention phrase is supplied",
       inv_custom(run_prose) is None)

# G) assert_resilient: passes a resilient agent, raises on a vulnerable one
def resilient(task):
    try:
        rows = get_rows("west")
    except Exception:
        return {"total": 0, "flagged": "tool failed"}
    if not rows:
        return {"total": 0, "flagged": "no rows"}
    return {"total": sum(rows), "n": len(rows)}

try:
    fl.assert_resilient(resilient, {}, faults=[fl.EmptyResult(targets=["get_rows"]),
                                               fl.NullResponse(targets=["get_rows"])])
    expect("assert_resilient passes a resilient agent", True)
except AssertionError:
    expect("assert_resilient passes a resilient agent", False)

def fragile(task):
    return {"n": len(get_rows("west"))}     # crashes on None, mis-answers on []

raised = False
try:
    fl.assert_resilient(fragile, {}, faults=[fl.NullResponse(targets=["get_rows"])])
except AssertionError:
    raised = True
expect("assert_resilient RAISES on a vulnerable agent", raised)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
