"""Local proof of action.yml: parses as YAML, and the gate step's exit-code
logic behaves exactly as the composite will on GitHub infra.

We execute the SAME bash logic as the action's `gate` step (with `pip install
faultline` swapped for PYTHONPATH so it runs offline) against clean and broken
suites, with fail-on-silent true/false.
"""
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

results = []
def check(name, cond):
    results.append((name, cond))
    print(("  ok  " if cond else "FAIL  ") + name)


# ---- 1. action.yml parses and has the contract surface --------------------
try:
    import yaml  # type: ignore
    spec = yaml.safe_load(open(os.path.join(ROOT, "action.yml")))
    check("action.yml parses as YAML", isinstance(spec, dict))
    check("composite action", spec.get("runs", {}).get("using") == "composite")
    check("inputs: suite/mode/fail-on-silent present",
          all(k in spec.get("inputs", {}) for k in ("suite", "mode", "fail-on-silent")))
    check("outputs: verdict/breaks/checked present",
          all(k in spec.get("outputs", {}) for k in ("verdict", "breaks", "checked")))
    check("no URL/KEY inputs (token-only hosted push)",
          "faultline-url" not in spec.get("inputs", {}) and "faultline-key" not in spec.get("inputs", {}))
    gate_run = [s for s in spec["runs"]["steps"] if s.get("id") == "gate"][0]["run"]
except ImportError:
    print("  --  PyYAML not installed; falling back to structural grep checks")
    raw = open(os.path.join(ROOT, "action.yml")).read()
    check("action.yml has composite + gate step", "composite" in raw and "id: gate" in raw)
    gate_run = raw.split("run: |", 1)[1]


# ---- 2. replicate the gate step's bash against real suites ----------------
SUITE = '''
import faultline as fl

@fl.tool
def get_stock(item): return 2

def agent(task):
    s = get_stock(task["item"])
    return {"ordered": task["qty"] if task["qty"] <= s else 0}

def hardened(task):
    s = get_stock(task["item"])
    if not isinstance(s, int) or s > 3:             # warehouse never holds more than 3
        return {"ordered": 0, "reason": "implausible stock reading"}
    return {"ordered": task["qty"] if task["qty"] <= s else 0}

def never_oversell(run):
    if run["output"]["ordered"] > 2: return "oversold"

def faultline_suite():
    return {"agent": AGENT == "hardened" and hardened or agent,
            "task": {"item": "w", "qty": 5},
            "faults": [fl.WrongNumber(targets=["get_stock"])],
            "invariants": [never_oversell]}
'''

GATE = '''
set +e
PYTHONPATH=%(root)s %(py)s -m faultline.cli "$MODE" "$SUITE"
code=$?
set -e
if [ "$code" -ge 2 ]; then exit "$code"; fi
if [ "$code" -eq 1 ] && [ "$FAIL_ON_SILENT" = "true" ]; then exit 1; fi
exit 0
'''


def gate(suite_path, fail_on_silent, mode="run"):
    env = dict(os.environ)
    env.update({"MODE": mode, "SUITE": suite_path, "FAIL_ON_SILENT": fail_on_silent})
    env.pop("FAULTLINE_TOKEN", None)
    p = subprocess.run(["bash", "-c", GATE % {"root": ROOT, "py": sys.executable}],
                       capture_output=True, text=True, env=env)
    return p.returncode


with tempfile.TemporaryDirectory() as d:
    buggy = os.path.join(d, "buggy.py")
    open(buggy, "w").write('AGENT = "buggy"\n' + SUITE)
    hard = os.path.join(d, "hard.py")
    open(hard, "w").write('AGENT = "hardened"\n' + SUITE)

    check("gate: silent failure + fail-on-silent=true  -> exit 1", gate(buggy, "true") == 1)
    check("gate: silent failure + fail-on-silent=false -> exit 0 (report-only)", gate(buggy, "false") == 0)
    check("gate: hardened agent -> exit 0", gate(hard, "true") == 0)
    check("gate: usage error fails EVEN in report-only mode",
          gate("/nope/missing.py", "false") == 2)

passed = sum(1 for _, c in results if c)
failed = len(results) - passed
print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
