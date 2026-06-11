"""Test: replay(transform=...) — behavioral drift after context compression.

Discipline (per the Director): prove the transform actually mutates the replayed
input AND that an IDENTITY transform is a no-op (no phantom drift), and that the
result is deterministic. Pure faultline — runs on Python 3.9.

Models the crewAI #5155 class: an agent whose decision silently flips when its
context is compressed/rotated, with no error raised.
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


# An agent whose decision depends on how much context it has (compression-sensitive).
def agent(task):
    ctx = task.get("context", "")
    return {"decision": "detailed" if len(ctx) >= 20 else "brief", "ctx_len": len(ctx)}


WATCH = lambda out: {"decision": out["decision"]}

rec = fl.record(agent, {"context": "x" * 50})            # full context -> "detailed"
expect("baseline records the full-context decision", rec["output"]["decision"] == "detailed")

# identity transform -> guaranteed no-op (no phantom drift)
r_identity = fl.replay(agent, rec, watch=WATCH, transform=lambda t: dict(t))
expect("identity transform is a no-op (no phantom drift)", not r_identity.regressed())

# no transform at all -> also a no-op
r_none = fl.replay(agent, rec, watch=WATCH)
expect("no transform is a no-op", not r_none.regressed())

# compression transform -> the decision silently flips -> drift caught
compress = lambda t: {"context": t["context"][:5]}       # 50 chars -> 5 chars
r_drift = fl.replay(agent, rec, watch=WATCH, transform=compress)
expect("context-compression drift IS caught (decision flipped, no error)", r_drift.regressed())
expect("the drift finding names the silently-changed decision",
       any("decision" in f for f in r_drift.findings))

# prove the transform actually mutated the replayed input (non-vacuous)
expect("the transform really shrank the context the agent saw",
       r_drift.new["output"]["ctx_len"] == 5 and rec["output"]["ctx_len"] == 50)

# determinism: same transform -> same verdict, twice
r_a = fl.replay(agent, rec, watch=WATCH, transform=compress)
r_b = fl.replay(agent, rec, watch=WATCH, transform=compress)
expect("drift detection is deterministic (identical verdicts across runs)",
       r_a.regressed() == r_b.regressed() == True and r_a.findings == r_b.findings)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
