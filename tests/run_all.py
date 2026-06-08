"""Run faultline's entire test suite — one command. (No API needed; all deterministic.)"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = [
    ("core engine — check (chaos)", "smoke_test.py"),
    ("invariant library", "test_invariants.py"),
    ("modes — probe / fuzz / replay / mine", "test_modes.py"),
    ("scenarios — Method A (honest inputs)", "test_scenarios.py"),
]
print("faultline — full test suite")
print("=" * 56)
all_ok = True
for name, f in SUITES:
    p = subprocess.run([sys.executable, os.path.join(HERE, f)], capture_output=True, text=True)
    tally = [l for l in p.stdout.strip().splitlines() if "passed" in l]
    ok = p.returncode == 0
    all_ok = all_ok and ok
    print("  %s  %-40s %s" % ("PASS" if ok else "FAIL", name, tally[-1] if tally else ""))
print("=" * 56)
print("ALL GREEN ✓" if all_ok else "SOME FAILED ✗")
sys.exit(0 if all_ok else 1)
