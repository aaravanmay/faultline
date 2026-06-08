"""faultline command-line interface.

    faultline demo                 run the built-in offline demo (no API key)
    faultline run <file.py>        run a faultline suite defined in <file.py>
    faultline version

A *suite file* defines a function ``faultline_suite()`` returning a dict:

    def faultline_suite():
        return {
            "agent": my_agent,                # callable: agent(task) -> output
            "task":  {...},                   # passed to the agent unchanged
            "faults": [fl.WrongNumber(...), fl.Timeout(), ...],
            "invariants": [my_invariant],     # optional
            "trials": 5,                      # optional
        }

Exit code is non-zero if any SILENT failure (FAIL) or CRASH is found, so
``faultline run`` gates CI / a GitHub Action out of the box.
"""
from __future__ import annotations

import importlib.util
import os
import sys

from . import __version__
from .runner import check

USAGE = __doc__


def _run_suite(suite, _push=False) -> int:
    agent = suite["agent"]
    task = suite.get("task")
    faults = suite["faults"]
    invariants = suite.get("invariants")
    trials = suite.get("trials", 5)
    import time as _time
    _t0 = _time.perf_counter()
    result = check(agent, task, faults, invariants=invariants, trials=trials)
    duration_ms = int((_time.perf_counter() - _t0) * 1000)
    result.report()
    if _push or os.environ.get("FAULTLINE_TOKEN"):
        from . import report as _report
        agent_name = suite.get("name") or getattr(agent, "__name__", "agent")
        ok, msg = _report.push_from_env(result, agent=agent_name, trials=trials, duration_ms=duration_ms)
        if ok is None:
            print("\nfaultline: results not pushed (%s). Set FAULTLINE_URL/KEY/TOKEN to send them to your dashboard." % msg)
        elif ok:
            print("\nfaultline: results pushed to your dashboard ✓")
        else:
            print("\nfaultline: push failed -> %s" % msg)
    bad = [r for r in result.rows if r["verdict"] in ("FAIL", "CRASH")]
    if bad:
        print("\nfaultline: %d fault(s) not handled -> exit 1" % len(bad))
        return 1
    print("\nfaultline: all faults handled -> exit 0")
    return 0


def _load_suite(path):
    if not os.path.exists(path):
        print("faultline: no such file: %s" % path, file=sys.stderr)
        return None
    spec = importlib.util.spec_from_file_location("_faultline_suite_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    fn = getattr(mod, "faultline_suite", None)
    if fn is None:
        print("faultline: %s defines no faultline_suite() function" % path, file=sys.stderr)
        return None
    return fn()


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "help"

    if cmd in ("version", "--version", "-V"):
        print("faultline %s" % __version__)
        return 0

    if cmd == "demo":
        from .examples.quickstart import faultline_suite
        print("faultline demo -- a tiny offline agent, no API key needed\n")
        return _run_suite(faultline_suite(), _push=("--push" in argv))

    if cmd == "run":
        _push = "--push" in argv
        args = [a for a in argv[1:] if a != "--push"]
        if not args:
            print("faultline: 'run' needs a file, e.g. faultline run suite.py", file=sys.stderr)
            return 2
        suite = _load_suite(args[0])
        if suite is None:
            return 2
        return _run_suite(suite, _push=_push)

    if cmd in ("help", "-h", "--help"):
        print(USAGE)
        return 0

    print("faultline: unknown command %r\n" % cmd, file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
