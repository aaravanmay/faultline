"""Test: faultline init — scaffolds a suite + CI, idempotent, never overwrites. Pure faultline."""
import ast
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from faultline.scaffold import init

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


tmp = tempfile.mkdtemp()
try:
    created, skipped = init(tmp)
    suite = os.path.join(tmp, "faultline_suite.py")
    wf = os.path.join(tmp, ".github", "workflows", "faultline.yml")
    expect("creates faultline_suite.py", os.path.exists(suite))
    expect("creates the CI workflow", os.path.exists(wf))
    expect("reports 2 created, 0 skipped", len(created) == 2 and len(skipped) == 0)

    src = open(suite).read()
    ast.parse(src)  # must be valid python
    expect("scaffolded suite defines faultline_suite()", "def faultline_suite()" in src)
    expect("scaffolded suite is importable shape (has agent + faults)",
           "def agent(" in src and "faults" in src)
    wfsrc = open(wf).read()
    expect("CI workflow runs the suite", "faultline run faultline_suite.py" in wfsrc)

    # idempotent: a second init creates nothing and skips both
    created2, skipped2 = init(tmp)
    expect("idempotent: second init creates nothing", len(created2) == 0)
    expect("idempotent: second init skips both files", len(skipped2) == 2)

    # never overwrites a user's edits
    with open(suite, "w") as f:
        f.write("# my edits\n")
    init(tmp)
    expect("never overwrites user edits", open(suite).read() == "# my edits\n")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
