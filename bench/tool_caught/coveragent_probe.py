"""faultline catching the real cover-agent stale-report bug (no LLM; needs the qodo-cover fork on PYTHONPATH).

Rule it checks: a coverage report that's older than the test run is STALE and must be rejected.
The REAL cover-agent only logs a warning and accepts it - so a freshly written test gets silently
thrown away for the wrong reason.
"""
import os, tempfile
from unittest.mock import MagicMock
import faultline as fl
from cover_agent.coverage_processor import CoverageProcessor  # real, unpatched (qodo-cover fork on main)


def freshness_check(test_time_offset_ms):
    d = tempfile.mkdtemp(); p = os.path.join(d, "cov.xml"); open(p, "w").write("<coverage></coverage>")
    stub = MagicMock(); stub.file_path = p
    test_time_ms = int(os.path.getmtime(p) * 1000) + test_time_offset_ms
    try:
        CoverageProcessor.verify_report_update(stub, test_time_ms)
        return "accepted"
    except AssertionError:
        return "rejected"


def stale_report_must_be_rejected(inp, out, err):
    if inp > 0 and err is None and out == "accepted":   # inp>0 => the report is older than the test run (stale)
        return "a stale coverage report (test ran %dms after the report) was silently accepted" % inp


fl.probe(freshness_check, fl.mutations(-1000, ("report-is-stale", lambda b: 5000)),
         [stale_report_must_be_rejected], label="cover-agent: stale report rejection", unpack=False).report()
