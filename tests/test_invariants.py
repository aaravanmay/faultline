"""Tests for faultline.invariants — the reusable, deterministic invariants distilled from
the real silent failures we found in popular OSS agents.

Each invariant is checked BOTH ways: it must fire on the bug, and stay quiet when fine
(no crying wolf). Run: python3 tests/test_invariants.py  (expects all passed).
"""
from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faultline as fl


def _run(events=None, output=None, error=None):
    return {"events": events or [], "output": output, "error": error}


def _ev(tool, result, args=None, kwargs=None):
    return {"tool": tool, "args": args or [], "kwargs": kwargs or {}, "result": result}


results = []
def check(name, cond):
    results.append((name, cond))
    print(("  ok  " if cond else "FAIL  ") + name)


# --- numeric_answer_finite (pandas-ai: NaN-as-valid-number) -------------------
inv = fl.numeric_answer_finite()
check("finite: NaN output fires", inv(_run(output=float("nan"))) is not None)
check("finite: inf output fires", inv(_run(output=float("inf"))) is not None)
check("finite: {'value': nan} fires", inv(_run(output={"value": float("nan")})) is not None)
check("finite: normal 42 is quiet", inv(_run(output=42)) is None)
check("finite: '3.14' string is quiet", inv(_run(output="the answer is 3.14")) is None)
check("finite: non-numeric output is quiet", inv(_run(output="hello world")) is None)


# --- abstain_when_context_empty (GPT-R/STORM/LlamaIndex fabrication) ----------
inv = fl.abstain_when_context_empty(tools=["search", "scrape"])
empty_ctx = [_ev("search", []), _ev("scrape", "")]
long_answer = "X is definitely true. " * 30          # ~600 chars, confident
check("abstain: empty ctx + long confident answer fires",
      inv(_run(events=empty_ctx, output=long_answer)) is not None)
check("abstain: empty ctx + proper abstention is quiet",
      inv(_run(events=empty_ctx, output="I could not find any sources for this.")) is None)
check("abstain: real ctx present is quiet",
      inv(_run(events=[_ev("search", ["a real hit"])], output=long_answer)) is None)
check("abstain: retrieval not used is quiet",
      inv(_run(events=[_ev("other", "x")], output=long_answer)) is None)


# --- no_poison_parroting (WrongNumber/StaleData echoed verbatim) --------------
inv = fl.no_poison_parroting(targets=["get_price"])
check("parrot: corrupted value echoed in output fires",
      inv(_run(events=[_ev("get_price", "999999")], output="The price is 999999 dollars.")) is not None)
check("parrot: value not echoed is quiet",
      inv(_run(events=[_ev("get_price", "999999")], output="I'm not certain about the price.")) is None)


# --- no_silent_shrink (Aider data loss) --------------------------------------
inv = fl.no_silent_shrink(read_tools=["read_file"], write_tools=["write_file"])
big = "line\n" * 100        # 500 chars read
check("shrink: write << read fires",
      inv(_run(events=[_ev("read_file", big), _ev("write_file", None, args=["line\n" * 5])])) is not None)
check("shrink: write ~ read is quiet",
      inv(_run(events=[_ev("read_file", big), _ev("write_file", None, args=["line\n" * 95])])) is None)
check("shrink: no read event is quiet",
      inv(_run(events=[_ev("write_file", None, args=["x"])])) is None)


# --- end-to-end: invariant plugs into fl.check() ------------------------------
@fl.tool
def fetch_total(_q):
    return 100  # baseline real value

def agent(task):
    total = fetch_total(task)
    return {"value": total / 0 if total == 0 else total}  # not the point; just exercises wiring

res = fl.check(
    agent, "sum sales",
    faults=[fl.WrongNumber(factor=0, targets=["fetch_total"])],   # forces total -> 0 -> nan path
    invariants=[fl.numeric_answer_finite()],
    trials=2,
)
check("e2e: fl.check runs with a library invariant", isinstance(res, fl.Result))


passed = sum(1 for _, c in results if c)
total = len(results)
print("\n%d passed, %d failed" % (passed, total - passed))
sys.exit(0 if passed == total else 1)
