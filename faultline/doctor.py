"""faultline doctor — a preflight that diagnoses whether faultline can test your agent.

The #1 first-run failure is "no wrapped tools fired" / "fault never reached" — which today only
surfaces *after* a confusing run. `doctor` runs your agent ONCE (no faults injected, read-only) and
turns that into an upfront, actionable checklist.

    faultline doctor my_agent.py:agent --task '{"sku": "A-12"}'
    fl.doctor(agent, {"sku": "A-12"}).report()
"""
from __future__ import annotations

import inspect
import platform
import sys

from .trace import run_once

# Types the value-corruption faults can actually reach (mirrors faults.py).
_CORRUPTIBLE = (int, float, str, bytes, list, tuple, dict, set, frozenset)


def _is_corruptible(v):
    if isinstance(v, _CORRUPTIBLE):
        return True
    if (getattr(type(v), "__module__", "") or "").startswith("pandas"):
        return True
    return False


def _version():
    try:
        import faultline
        return getattr(faultline, "__version__", "?")
    except Exception:
        return "?"


class DoctorReport:
    """Result of fl.doctor — a list of (label, detail, status) checks + a ready verdict."""

    _ICON = {"ok": "✓", "warn": "⚠", "fail": "✗", "info": "·"}

    def __init__(self, checks, ready):
        self.checks = checks
        self.ready = ready

    def ok(self):
        return self.ready

    def report(self, write=True):
        lines = ["", "faultline · doctor  (preflight — no faults injected, read-only)", "=" * 64]
        for label, detail, status in self.checks:
            lines.append("%s  %-34s %s" % (self._ICON.get(status, "?"), label, detail))
        lines.append("-" * 64)
        if self.ready:
            lines.append("✓ READY — run `faultline scan` (or fl.check) to break the tools and test it.")
        else:
            lines.append("✗ NOT READY — fix the ✗ item(s) above, then re-run doctor.")
        out = "\n".join(lines)
        if write:
            print(out)
        return out


def doctor(agent, task=None):
    """Run *agent* once (no faults) and report whether faultline can meaningfully test it."""
    checks = [("faultline version", _version(), "info")]
    py_ok = sys.version_info >= (3, 9)
    checks.append(("python", platform.python_version() + ("" if py_ok else "  (faultline needs 3.9+)"),
                   "info" if py_ok else "fail"))

    run = run_once(agent, task or {})
    out = run["output"]

    # async agent — the un-awaited-coroutine trap
    if inspect.iscoroutine(out):
        out.close()
        checks.append(("agent type",
                       "ASYNC (returns a coroutine) — not supported. Wrap it: "
                       "lambda t: asyncio.run(my_agent(t))", "fail"))
        return DoctorReport(checks, ready=False)

    if run["error"] is not None:
        checks.append(("agent runs on clean data", "CRASHED on the baseline: %s" % run["error"], "fail"))
    else:
        checks.append(("agent runs on clean data", "ok", "ok"))

    events = run["events"]
    names = sorted(set(ev["tool"] for ev in events))
    if not names:
        checks.append(("wrapped tools fired",
                       "NONE — faultline has nothing to break. Wrap your tool calls with "
                       "@fl.tool or fl.wrap(...).", "fail"))
        return DoctorReport(checks, ready=False)
    checks.append(("wrapped tools fired", "%d: %s" % (len(names), ", ".join(names)), "ok"))

    actions = sorted(set(ev["tool"] for ev in events if ev.get("is_action")))
    if actions:
        checks.append(("action tools (stubbed — never fire for real)", ", ".join(actions), "ok"))

    # per-tool return type: corruptible vs an uncorruptible coverage gap
    first_result = {}
    for ev in events:
        first_result.setdefault(ev["tool"], ev["result"])
    gaps = [n for n in names if not _is_corruptible(first_result.get(n))]
    if gaps:
        for n in gaps:
            checks.append(("tool '%s' return" % n,
                           "%s — faults may not reach it (coverage gap). Materialize it "
                           "(e.g. list(...)) or assert an invariant." % type(first_result[n]).__name__,
                           "warn"))
    else:
        checks.append(("tool return types", "all corruptible — faults will reach them", "ok"))

    ready = not any(status == "fail" for _, _, status in checks)
    return DoctorReport(checks, ready)
