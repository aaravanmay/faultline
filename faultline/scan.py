"""faultline scan — zero-oracle, zero-suite-file silent-failure check.

Point it at your agent function. It runs one fault-free baseline to discover
which of your faultline-wrapped tools fire, hits each with the default fault
battery, and runs the built-in deterministic detector with NO hand-written
invariants. The cleanest "is my agent resilient?" answer with the least setup.

    import faultline as fl
    result, tools = fl.scan(my_agent, {"item": "widget"})
    result.report()

CLI:
    faultline scan path/to/agent.py:my_agent --task '{"item": "widget"}'

What it relies on: your tools are wrapped with @fl.tool or fl.wrap(fn) (one
decorator) so faultline can intercept them. It does NOT need a suite file or
invariants — the no-oracle layers (action-divergence, leaf-parroting,
derived-value) carry the detection. For text-shape guarantees an agent must
keep, add an invariant via the full `faultline run` path; scan is the fast,
zero-config first look, strongest on action / numeric agents.
"""
from __future__ import annotations

from .faults import (
    EmptyResult, NullResponse, ServerError, StaleData, Timeout, Truncate, WrongNumber,
)
from .runner import check
from .trace import run_once


def discover_tools(agent, task=None):
    """Run one fault-free baseline and return (distinct tool names that fired, baseline run)."""
    baseline = run_once(agent, task)
    seen = []
    for ev in baseline.get("events", []):
        nm = ev.get("tool")
        if nm and nm not in seen:
            seen.append(nm)
    return seen, baseline


def default_battery(tool_names=None):
    """The zero-config fault battery, scoped to *tool_names* (all tools if None)."""
    t = list(tool_names) if tool_names else None
    return [
        WrongNumber(targets=t),
        StaleData(targets=t),
        Truncate(targets=t),
        NullResponse(targets=t),
        EmptyResult(targets=t),
        Timeout(targets=t),
        ServerError(targets=t),
    ]


def scan(agent, task=None, trials=3):
    """Zero-oracle scan.

    Discover the agent's faultline-wrapped tools, hit each with the default
    fault battery, and run the built-in detector with NO invariants.

    Returns ``(result, tool_names)``. ``tool_names`` is ``[]`` when the agent
    has no wrapped tools — in that case the result is vacuous (there was
    nothing to corrupt); wrap your tool calls with ``@fl.tool`` / ``fl.wrap``
    first.
    """
    tool_names, _baseline = discover_tools(agent, task)
    faults = default_battery(tool_names)
    result = check(agent, task, faults, invariants=[], trials=trials)
    return result, tool_names
