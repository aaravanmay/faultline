"""Run faultline's entire test suite — one command. (No API needed; all deterministic.)"""
import os, subprocess, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SUITES = [
    ("core engine — check (chaos)", "smoke_test.py"),
    ("invariant library", "test_invariants.py"),
    ("modes — probe / fuzz / replay / mine", "test_modes.py"),
    ("scenarios — Method A (honest inputs)", "test_scenarios.py"),
    ("RAG integration template example", "test_rag_example.py"),
    ("vs-eval head-to-head example", "test_vs_eval.py"),
    ("multi-tool cascade example", "test_multi_tool.py"),
    ("quickstart notebook", "test_notebook.py"),
    ("scan — zero-oracle quickstart", "test_scan.py"),
    ("doctor — preflight diagnosis", "test_doctor.py"),
    ("init — scaffold suite + CI", "test_init.py"),
    ("adapters — auto-instrument tools", "test_adapters.py"),
    ("langgraph adapter (real lib; skips on py<3.10)", "test_langgraph_adapter.py"),
    ("langchain adapter (real lib; skips on py<3.10)", "test_langchain_real.py"),
    ("llamaindex adapter (real lib; skips on py<3.10)", "test_llamaindex_real.py"),
    ("pydantic-ai adapter (real lib; skips on py<3.10)", "test_pydantic_ai_real.py"),
    ("crewai adapter (real lib; skips on py<3.10)", "test_crewai_real.py"),
    ("loud results — no false green", "test_loud_result.py"),
    ("report wording — user-facing message surface", "test_report_output.py"),
    ("CLI — all modes gate CI", "test_cli_modes.py"),
    ("declarative faultline.json config", "test_config.py"),
    ("GitHub Action — gate semantics", "test_action_local.py"),
    ("wave-3 detector — display-args / derived / pandas / dict-fuzz", "test_wave3_detector.py"),
    ("fabrication detector + EmptyResult fault", "test_fabrication.py"),
    ("fault library — edge-case depth (Decimal, Truncate, finite)", "test_fault_edges.py"),
    ("hardening — adversarial-QA regression guards", "test_hardening.py"),
    ("concurrency — thread-isolated fault injection", "test_concurrency.py"),
    ("drift — replay(transform=) context compression", "test_drift.py"),
    ("runtime guard — shadow / enforce seatbelt", "test_guard.py"),
    ("attest / verify — tamper-evident report", "test_attest.py"),
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
