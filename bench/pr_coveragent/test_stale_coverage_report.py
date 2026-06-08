"""Regression test: a stale coverage report must raise, not be silently accepted.

verify_report_update's own docstring says it "Raises: AssertionError ... if the coverage
report ... was not updated after the test command." The implementation only logged a
warning and returned, so process_coverage_report then parsed the STALE report and the
caller silently rolled back the newly generated test ("coverage did not increase").

Calls the method via the unbound method with a mock self (only file_path + logger are used):
  with the fix -> PASS (raises AssertionError on a stale report)
  without it   -> FAIL (only warns; does not raise)
"""
from unittest.mock import MagicMock

import pytest

from cover_agent.coverage_processor import CoverageProcessor


def test_stale_report_raises(tmp_path):
    xml = tmp_path / "cov.xml"
    xml.write_text("<coverage></coverage>")
    stub = MagicMock()
    stub.file_path = str(xml)
    # Pretend the test command ran AFTER the report's mtime -> report is stale.
    test_time_ms = int(xml.stat().st_mtime * 1000) + 5000
    with pytest.raises(AssertionError):
        CoverageProcessor.verify_report_update(stub, test_time_ms)
