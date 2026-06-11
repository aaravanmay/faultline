"""faultline.assert_resilient — drop faultline into an existing test suite.

No plugin to install, no runner to learn: it's a plain assertion that raises
(with the full report) on any silent failure or crash. Works in pytest,
unittest, or a bare script.

    import faultline as fl

    def test_my_agent_is_resilient():
        fl.assert_resilient(my_agent, {"q": "weather in NYC"})

With no `faults` given it uses the zero-config scan battery (auto-discovers the
agent's wrapped tools). Pass `faults=` / `invariants=` for a targeted check.
"""
from __future__ import annotations

import contextlib
import io

from .runner import check
from .scan import scan as _scan


def assert_resilient(agent, task=None, faults=None, invariants=None, trials=3, msg=None):
    """Raise AssertionError if *agent* has any SILENT failure or CRASH under faults.

    faults=None  -> zero-config: auto-discover the agent's wrapped tools and hit them
                    with the default battery (same as `faultline scan`).
    faults=[...] -> a targeted check (same as `fl.check`).

    Returns the Result on success (so you can assert further if you want).
    """
    if faults is None:
        result, tool_names = _scan(agent, task, trials=trials)
        if not tool_names:
            raise AssertionError(
                "faultline: no @fl.tool / fl.wrap-wrapped tools fired in this agent — "
                "nothing to inject. Wrap your tool calls so faultline can test them.")
    else:
        result = check(agent, task, faults, invariants=invariants, trials=trials)

    # A test gate is conservative: fail on a SILENT verdict, a CRASH, OR any single SILENT trial.
    # A non-deterministic agent that silently does the wrong thing on a *minority* of trials
    # aggregates to INCONCLUSIVE (not a majority-SILENT verdict) — but an intermittent silent
    # failure is still a real bug, so we catch it here even though Result.ok() tolerates it.
    bad = [r for r in result.rows
           if r["verdict"] in ("FAIL", "CRASH") or "SILENT" in r.get("trials", [])]
    if bad:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            try:
                result.report()
            except Exception:
                pass
        n_silent_only = sum(1 for r in bad
                            if r["verdict"] not in ("FAIL", "CRASH") and "SILENT" in r.get("trials", []))
        extra = (" (incl. %d intermittent — silent on some trials, not a majority)" % n_silent_only
                 if n_silent_only else "")
        header = msg or ("faultline: agent is not resilient — %d fault(s) it silently mishandled%s"
                         % (len(bad), extra))
        raise AssertionError("%s\n%s" % (header, buf.getvalue()))
    return result
