"""Tests for faultline's testing MODES: probe, fuzz, replay, mine. Deterministic, no API.

Each mode is checked BOTH ways: it must catch the planted failure AND stay quiet when fine.
Run:  python3 tests/test_modes.py   (expects all passed).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faultline as fl

results = []
def check(name, cond):
    results.append((name, bool(cond)))
    print(("  ok  " if cond else "FAIL  ") + name)


# ---------- mode 2: probe (property / metamorphic) ----------
def _chunk(overlap):
    # planted bug: a fractional overlap >= 1 silently produces nothing
    return [] if (isinstance(overlap, float) and overlap >= 1) else ["a", "b"]

def _nonempty(inp, out, err):
    if err is None and isinstance(out, list) and not out:
        return "silently produced 0 chunks"

_p = fl.probe(_chunk, fl.mutations(0, ("frac>=1", lambda b: 1.5)), [_nonempty], unpack=False)
check("probe: baseline passes", _p.rows[0]["status"] == "PASS")
check("probe: catches the edge-input bug", len(_p.silent()) == 1)


# ---------- mode 3: fuzz (auto-generated edge inputs) ----------
_f = fl.fuzz(_chunk, 0, [_nonempty])
check("fuzz: baseline passes", _f.rows[0]["status"] == "PASS")
check("fuzz: auto-discovers a breaking input", len(_f.breakers()) >= 1)
check("fuzz: tried multiple generated inputs", _f.tried > 3)


# ---------- mode 4: replay (regression after a change) ----------
@fl.tool
def _tool_x():
    return 1

def _agent_v1(task):
    _tool_x()
    return {"decision": "A"}

def _agent_v2(task):           # regressed
    _tool_x()
    return {"decision": "B"}

_rec = fl.record(_agent_v1, "task")
_w = lambda o: {"decision": o["decision"]}
check("replay: catches a silent regression", fl.replay(_agent_v2, _rec, watch=_w).regressed())
check("replay: no false positive on the same agent", not fl.replay(_agent_v1, _rec, watch=_w).regressed())

# disk round-trip (flightlog loop)
import tempfile
from faultline.replay import save_trace, load_trace
_path = os.path.join(tempfile.gettempdir(), "fl_test_trace.json")
save_trace(_rec, _path)
_loaded = load_trace(_path)
check("flightlog: saved trace replays + catches regression", fl.replay(_agent_v2, _loaded, watch=_w).regressed())


# ---------- mode 5: mine (invariant mining) ----------
@fl.tool
def _step_a():
    return 1

@fl.tool
def _step_b():
    return 2

def _good(task):
    _step_a(); _step_b()
    return {"status": "ok"}

def _regressed(task):          # skips step_a
    _step_b()
    return {"status": "ok"}

_spec = fl.mine(_good, ["t1", "t2"])
check("mine: learns at least the ordering rule", len(_spec.rules) >= 2)
check("mine: catches the regression (rule nobody wrote)", len(_spec.check(fl.run_once(_regressed, "t"))) >= 1)
check("mine: no false positive on a good run", len(_spec.check(fl.run_once(_good, "t"))) == 0)


passed = sum(1 for _, c in results if c)
print("\n%d passed, %d failed" % (passed, len(results) - passed))
sys.exit(0 if passed == len(results) else 1)
