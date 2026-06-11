"""Test: the RAG integration template catches the empty-retrieval fabrication. Pure faultline."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"))
import rag_pipeline as rag

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


bad, good = rag.main()
expect("buggy RAG generator is caught fabricating from empty retrieval", bool(bad.silent))
expect("grounded RAG generator (abstains) passes — no false alarm", not good.silent)
expect("faultline_check() helper returns a usable Result", bool(rag.faultline_check().rows))

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
