"""Test: edge-case depth on the fault library + invariants (characterizes behavior). Pure faultline.

Includes the B8 finding: WrongNumber now corrupts `Decimal` (the standard money type), which it
silently passed through before — a coverage gap for the financial agents faultline targets.
"""
import os
import sys
from decimal import Decimal

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


_H = lambda fault, v: fault.hit("t", [], {}, v)

# --- WrongNumber edges ---
wn = fl.WrongNumber(factor=3.0)
expect("WrongNumber corrupts Decimal (money type — was a gap)", _H(wn, Decimal("2.50")) == Decimal("7.50"))
expect("WrongNumber corrupts a nested Decimal in a dict",
       _H(wn, {"price": Decimal("10.00")})["price"] == Decimal("30.00"))
expect("WrongNumber corrupts a negative number", _H(wn, -5) == -15)
expect("WrongNumber turns 0 into a clearly-wrong value (no silent no-op)", _H(wn, 0) == 3)
expect("WrongNumber recurses into nested dicts", _H(wn, {"a": {"b": 4}}) == {"a": {"b": 12}})
expect("WrongNumber leaves non-numbers untouched", _H(wn, "hello") == "hello")
expect("WrongNumber leaves bools untouched (a bool isn't a quantity)", _H(wn, True) is True)

# --- Truncate edges ---
tr = fl.Truncate()
expect("Truncate of a 1-element list -> [] (half of 1)", _H(tr, ["x"]) == [])
expect("Truncate of a 1-key dict -> {}", _H(tr, {"a": 1}) == {})
expect("Truncate of an empty string -> ''", _H(tr, "") == "")
expect("Truncate of a non-sequence (number) passes through", _H(tr, 42) == 42)

# --- numeric_answer_finite edges ---
nf = fl.numeric_answer_finite()


def _run(out, err=None):
    return {"output": out, "events": [], "error": err}


expect("numeric_answer_finite fires on inf", nf(_run("the answer is inf")) is not None)
expect("numeric_answer_finite fires on nan", nf(_run("result: nan")) is not None)
expect("numeric_answer_finite is silent on a normal finite number", nf(_run("answer: 42")) is None)
expect("numeric_answer_finite is silent on a crash (separate failure)",
       nf(_run(None, err=ValueError("boom"))) is None)

# --- EmptyResult edges ---
er = fl.EmptyResult()
expect("EmptyResult empties a string to ''", _H(er, "hi") == "")
expect("EmptyResult zeroes a number", _H(er, 7) == 0)
expect("EmptyResult leaves a bool untouched", _H(er, True) is True)
expect("EmptyResult zeroes a Decimal", _H(er, Decimal("9.99")) == Decimal("0"))

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
