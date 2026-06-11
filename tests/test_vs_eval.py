"""Test: the faultline-vs-eval head-to-head — the eval passes, faultline catches. Pure faultline."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"))
import vs_eval

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


eval_ok, caught = vs_eval.main()
expect("the plain eval PASSES on clean data (its blind spot)", eval_ok is True)
expect("faultline CATCHES the silent failure the eval missed", caught is True)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
