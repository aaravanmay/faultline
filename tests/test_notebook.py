"""Test: the quickstart notebook is valid nbformat AND its code cells actually run + catch the bug."""
import contextlib
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples", "quickstart.ipynb")

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


nb = json.load(open(NB))
expect("quickstart.ipynb is nbformat 4", nb.get("nbformat") == 4)
expect("has code + markdown cells", any(c["cell_type"] == "code" for c in nb["cells"]))

# run the code cells (minus the %pip magic) and confirm they catch the silent failure
code = []
for c in nb["cells"]:
    if c["cell_type"] == "code":
        code += [ln for ln in c["source"] if not ln.strip().startswith("%")]
        code.append("\n")
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    exec(compile("".join(code), "nb", "exec"), {})
out = buf.getvalue()
expect("notebook code runs and catches a silent failure", "SILENT" in out and "silent failures caught: 1" in out)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
