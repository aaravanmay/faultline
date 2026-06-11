"""Test: the multi-tool cascade example catches a corrupted-price -> over-budget order. Pure faultline."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"))
import multi_tool_agent as mt

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


res = mt.main()
expect("catches the cascade (corrupted price -> wrong budget decision -> over-budget order)",
       bool(res.silent))
expect("the finding names the true over-budget total",
       any("1500" in r["detail"] for r in res.silent))

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
