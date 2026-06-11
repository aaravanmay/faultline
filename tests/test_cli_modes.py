"""CLI parity: every advertised testing mode runs as a subcommand and gates CI.

For each mode: a CLEAN suite must exit 0 and a BROKEN suite must exit 1 —
the exit code IS the product (it's what fails the build), so it gets tests.
Also verifies the GitHub Actions artifacts ($GITHUB_STEP_SUMMARY/$GITHUB_OUTPUT).
"""
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SUITE = '''
import faultline as fl

@fl.tool
def get_stock(item): return 2

def agent(task):
    s = get_stock(task["item"])
    return {"ordered": task["qty"] if task["qty"] <= s else 0}

def naive_agent(task):
    return {"ordered": task["qty"]}          # trusts input blindly -> oversells

def never_oversell(run):
    if run["output"]["ordered"] > 2: return "oversold"

def ok_fn(x): return x + 1
def bad_fn(x): return 1 // (x - x)           # always raises

def prop_no_raise(inp, out, err):
    if err is not None: return "raised %r" % err

def faultline_suite():
    return {"agent": agent, "task": {"item": "w", "qty": 5},
            "faults": [fl.WrongNumber(targets=["get_stock"])], "invariants": [never_oversell]}

def faultline_probe():
    return {"fn": BAD and bad_fn or ok_fn, "cases": [("a", (1,)), ("b", (2,))],
            "properties": [prop_no_raise]}

def faultline_fuzz():
    return {"fn": BAD and bad_fn or ok_fn, "base": 5, "properties": [prop_no_raise]}

def faultline_scenarios():
    return {"agent": BAD and naive_agent or agent,
            "cases": [{"item": "w", "qty": 5}], "invariants": [never_oversell]}

def faultline_replay():
    # record at qty=5 where the safe agent (orders 0) and the naive agent
    # (orders 5) genuinely diverge — replay must flag the naive one.
    rec = fl.record(agent, {"item": "w", "qty": 5})
    return {"agent": BAD and naive_agent or agent, "trace": rec,
            "watch": lambda o: {"ordered": o["ordered"]}}

def faultline_mine():
    return {"agent": agent, "good_tasks": [{"item": "w", "qty": 1}, {"item": "w", "qty": 2}]}
'''


def write_suite(d, bad):
    p = os.path.join(d, "s_%s.py" % ("bad" if bad else "ok"))
    with open(p, "w") as f:
        f.write("BAD = %r\n" % bad + SUITE)
    return p


def run_cli(args, env_extra=None):
    env = dict(os.environ)
    env["PYTHONPATH"] = ROOT
    env.pop("FAULTLINE_TOKEN", None)          # never push from tests
    if env_extra:
        env.update(env_extra)
    p = subprocess.run([sys.executable, "-m", "faultline.cli"] + args,
                       capture_output=True, text=True, env=env)
    return p.returncode


results = []
def check(name, cond):
    results.append((name, cond))
    print(("  ok  " if cond else "FAIL  ") + name)


with tempfile.TemporaryDirectory() as d:
    ok = write_suite(d, bad=False)
    bad = write_suite(d, bad=True)

    # chaos run/check: the resilient agent still FAILS under WrongNumber here
    # (it has no cross-check), so run exits 1 — that's the canonical gate.
    check("run: silent failure -> exit 1", run_cli(["run", ok]) == 1)
    check("check alias matches run", run_cli(["check", ok]) == 1)

    # per-subcommand --help dispatches and exits clean
    check("scan --help exits 0", run_cli(["scan", "--help"]) == 0)
    check("run --help exits 0", run_cli(["run", "--help"]) == 0)
    check("doctor --help exits 0", run_cli(["doctor", "--help"]) == 0)

    for mode in ("probe", "fuzz", "scenarios", "replay"):
        check("%s: clean -> exit 0" % mode, run_cli([mode, ok]) == 0)
        check("%s: broken -> exit 1" % mode, run_cli([mode, bad]) == 1)

    check("mine: informational -> exit 0", run_cli(["mine", ok]) == 0)
    check("unknown command -> exit 2", run_cli(["bogus"]) == 2)
    check("missing file -> exit 2", run_cli(["probe", "/nope/missing.py"]) == 2)
    check("missing mode fn -> exit 2", run_cli(["replay", os.path.join(ROOT, "faultline", "__init__.py")]) == 2)

    # GitHub Actions artifacts: summary + outputs written when env vars are set
    summ = os.path.join(d, "summary.md"); outp = os.path.join(d, "out.txt")
    run_cli(["probe", ok], {"GITHUB_STEP_SUMMARY": summ, "GITHUB_OUTPUT": outp})
    s = open(summ).read() if os.path.exists(summ) else ""
    o = open(outp).read() if os.path.exists(outp) else ""
    check("CI: step summary written", "faultline" in s and "verdict" in s.lower())
    check("CI: outputs written (verdict/breaks/checked)",
          "verdict=PASS" in o and "breaks=0" in o and "checked=" in o)


passed = sum(1 for _, c in results if c)
failed = len(results) - passed
print("\n%d passed, %d failed" % (passed, failed))
sys.exit(1 if failed else 0)
