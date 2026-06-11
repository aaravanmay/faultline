"""faultline command-line interface.

    faultline demo                 run the built-in offline demo (no API key)
    faultline init                 scaffold a faultline_suite.py + CI workflow (never overwrites)
    faultline doctor <file.py>:<fn> preflight: can faultline test this agent? (no faults injected)
    faultline scan <file.py>:<fn>  zero-config: break your agent's tools, no suite file needed
                                   (add --explain to see exactly what it corrupted + why each FAIL)
    faultline run <file.py>        chaos-test the suite in <file.py>  (alias: check)
                                   (or a declarative `faultline run config.json`)
    faultline attest <file.py>     run + write a tamper-evident faultline.report.json
    faultline verify <report.json> re-derive the hash, confirm the report is untampered
    faultline probe <file.py>      run honest edge cases    -> needs faultline_probe()
    faultline fuzz <file.py>       auto-generate edge inputs -> needs faultline_fuzz()
    faultline scenarios <file.py>  honest hard situations    -> needs faultline_scenarios()
    faultline replay <file.py>     re-run a recorded trace   -> needs faultline_replay()
    faultline mine <file.py>       learn rules from good runs -> needs faultline_mine()
    faultline version

Every testing subcommand exits non-zero when a silent failure (or crash) is
found, so any of them can gate CI. In GitHub Actions, a markdown verdict table
is written to $GITHUB_STEP_SUMMARY and counts to $GITHUB_OUTPUT automatically.

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
            print("\nfaultline: results not pushed (%s)." % msg)
        elif ok:
            print("\nfaultline: results pushed to your dashboard ✓")
        else:
            print("\nfaultline: push failed -> %s" % msg)
    bad = [r for r in result.rows if r["verdict"] in ("FAIL", "CRASH")]
    _ci_emit("chaos-check", len(bad), len(result.rows))
    if bad:
        print("\nfaultline: %d fault(s) not handled -> exit 1" % len(bad))
        return 1
    print("\nfaultline: all faults handled -> exit 0")
    return 0


def _run_attest(suite, out_path) -> int:
    """Run the suite (same gate semantics as run) AND write a tamper-evident
    faultline.report.json. Exit code follows the gate (non-zero on FAIL/CRASH),
    so `attest` still gates CI -- it is `run` plus a signed evidence file.
    """
    from . import attest as _attest

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

    agent_name = suite.get("name") or getattr(agent, "__name__", "agent")
    report = _attest.build_report(result, agent=agent_name,
                                  duration_ms=duration_ms, trials=trials)
    _attest.write_report(report, out_path)
    chash = report["attestation"]["content_hash"]
    n = len(report["body"].get("results", []))
    print("\nfaultline: wrote %s" % out_path)
    print("faultline: attested %d verdict(s) -- sha256 %s (tamper-evident, not a secret-key signature)"
          % (n, chash))

    bad = [r for r in result.rows if r["verdict"] in ("FAIL", "CRASH")]
    _ci_emit("attest", len(bad), len(result.rows), extra="content-hash `%s`" % chash)
    if bad:
        print("\nfaultline: %d fault(s) not handled -> exit 1 (report still written)" % len(bad))
        return 1
    print("\nfaultline: all faults handled -> exit 0")
    return 0


def _run_verify(report_path) -> int:
    """Load a faultline.report.json, recompute its content hash, and confirm it
    matches. Any edit (a flipped verdict, an altered number) changes the hash ->
    exit non-zero and name the mismatch. Clean report -> exit 0.
    """
    from . import attest as _attest

    if not os.path.exists(report_path):
        print("faultline: no such file: %s" % report_path, file=sys.stderr)
        return 2
    try:
        report = _attest.load_report(report_path)
    except Exception as exc:
        print("faultline: could not read %s as a report -- %s: %s"
              % (report_path, type(exc).__name__, exc), file=sys.stderr)
        return 2

    ok, msg = _attest.verify_report(report)
    if ok:
        print("faultline: %s" % msg)
        return 0
    print("faultline: VERIFY FAILED -- %s" % msg, file=sys.stderr)
    return 1


def _load_suite(path):
    if not os.path.exists(path):
        print("faultline: no such file: %s" % path, file=sys.stderr)
        return None
    spec = importlib.util.spec_from_file_location("_faultline_suite_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        print("faultline: error loading %s — %s: %s" % (path, type(exc).__name__, exc),
              file=sys.stderr)
        return None
    fn = getattr(mod, "faultline_suite", None)
    if fn is None:
        print("faultline: %s defines no faultline_suite() function" % path, file=sys.stderr)
        return None
    try:
        return fn()
    except Exception as exc:
        print("faultline: error in faultline_suite() of %s — %s: %s" % (path, type(exc).__name__, exc),
              file=sys.stderr)
        return None


def _load_fn(path, fn_name):
    """Load *fn_name*() from a suite file (same loader semantics as _load_suite)."""
    if not os.path.exists(path):
        print("faultline: no such file: %s" % path, file=sys.stderr)
        return None
    spec = importlib.util.spec_from_file_location("_faultline_mode_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        print("faultline: error loading %s — %s: %s" % (path, type(exc).__name__, exc),
              file=sys.stderr)
        return None
    fn = getattr(mod, fn_name, None)
    if fn is None:
        print("faultline: %s defines no %s() function" % (path, fn_name), file=sys.stderr)
        return None
    try:
        return fn()
    except Exception as exc:
        print("faultline: error in %s() of %s — %s: %s" % (fn_name, path, type(exc).__name__, exc),
              file=sys.stderr)
        return None


def _load_attr(path, attr_name):
    """Load *attr_name* from a file WITHOUT calling it (used by scan for the agent fn)."""
    if not os.path.exists(path):
        print("faultline: no such file: %s" % path, file=sys.stderr)
        return None
    spec = importlib.util.spec_from_file_location("_faultline_scan_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        print("faultline: error loading %s — %s: %s" % (path, type(exc).__name__, exc),
              file=sys.stderr)
        return None
    fn = getattr(mod, attr_name, None)
    if fn is None:
        print("faultline: %s defines no %s" % (path, attr_name), file=sys.stderr)
        return None
    if not callable(fn):
        print("faultline: %s in %s is not callable" % (attr_name, path), file=sys.stderr)
        return None
    return fn


def _parse_task(raw):
    """Parse a --task value: JSON if it parses, otherwise the bare string."""
    if raw is None:
        return None
    try:
        import json
        return json.loads(raw)
    except Exception:
        return raw


def _run_scan(target, task, trials=3, explain=False):
    """Drive `faultline scan FILE.py:agent_fn`."""
    if ":" not in target:
        print("faultline: scan target must be FILE.py:agent_function "
              "(e.g. agent.py:my_agent)", file=sys.stderr)
        return 2
    path, fn_name = target.rsplit(":", 1)
    fn = _load_attr(path, fn_name)
    if fn is None:
        return 2
    from .scan import scan as _scan
    try:
        result, tool_names = _scan(fn, task, trials=trials)
    except Exception as exc:
        print("faultline: scan failed — %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2
    if not tool_names:
        print("faultline: no faultline-wrapped tools fired in %s().\n"
              "  Wrap your tool calls with @fl.tool or fl.wrap(fn) so faultline can inject\n"
              "  faults, then re-run. (scan needs at least one wrapped tool to corrupt.)"
              % fn_name, file=sys.stderr)
        return 2
    print("faultline scan -- %d wrapped tool(s): %s\n" % (len(tool_names), ", ".join(tool_names)))
    result.report()
    if explain:
        result.explain()
    # Honesty note: a fault that never reached a tool is a COVERAGE GAP, not resilience.
    not_reached = [r for r in result.rows
                   if r["verdict"] == "PASS" and "never reached" in (r.get("detail") or "")]
    if not_reached:
        print("\nnote: %d fault(s) never reached a tool (%s) — the agent doesn't call it, or there was"
              "\n      nothing to corrupt. That's a coverage gap, not proof of resilience."
              % (len(not_reached), ", ".join(r["fault"] for r in not_reached)))
    # Gate on a SILENT/CRASH verdict OR any single SILENT trial (an intermittent silent failure
    # aggregates to INCONCLUSIVE but is still a real bug — don't let it slip past CI).
    bad = [r for r in result.rows
           if r["verdict"] in ("FAIL", "CRASH") or "SILENT" in r.get("trials", [])]
    _ci_emit("scan", len(bad), len(result.rows))
    if bad:
        print("\nfaultline: %d fault(s) not handled -> exit 1" % len(bad))
        return 1
    print("\nfaultline: all faults handled -> exit 0")
    return 0


def _ci_emit(mode, breaks, total_checked, extra=None):
    """Write CI-friendly artifacts when running inside GitHub Actions.

    - $GITHUB_STEP_SUMMARY gets a small markdown verdict table.
    - $GITHUB_OUTPUT gets machine-readable counts for downstream steps.
    Silently does nothing outside CI.
    """
    verdict = "PASS" if breaks == 0 else "FAIL"
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a") as f:
                f.write("\n### faultline · %s\n\n" % mode)
                f.write("| verdict | silent/broken | checked |\n|---|---|---|\n")
                f.write("| %s %s | %d | %d |\n" % ("✅" if breaks == 0 else "⚠️", verdict, breaks, total_checked))
                if extra:
                    f.write("\n%s\n" % extra)
        except Exception:
            pass
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        try:
            with open(output_path, "a") as f:
                f.write("verdict=%s\nbreaks=%d\nchecked=%d\nmode=%s\n" % (verdict, breaks, total_checked, mode))
        except Exception:
            pass


def _run_mode(mode, path):
    """Run one of the non-chaos testing modes from a suite file. Returns exit code."""
    from . import probe, fuzz, scenarios, replay, mine, load_trace

    cfg = _load_fn(path, "faultline_%s" % mode)
    if cfg is None:
        return 2
    if not isinstance(cfg, dict):
        print("faultline: faultline_%s() must return a dict of arguments" % mode, file=sys.stderr)
        return 2

    try:
        if mode == "probe":
            res = probe(cfg["fn"], cfg["cases"], cfg["properties"],
                        label=cfg.get("label", "probe"), unpack=cfg.get("unpack", True))
        elif mode == "fuzz":
            res = fuzz(cfg["fn"], cfg["base"], cfg["properties"],
                       mutators=cfg.get("mutators"), include_pairs=cfg.get("include_pairs", True),
                       label=cfg.get("label", "fuzz"), unpack=cfg.get("unpack", False))
        elif mode == "scenarios":
            res = scenarios(cfg["agent"], cfg["cases"], cfg["invariants"],
                            label=cfg.get("label", "scenarios"))
        elif mode == "replay":
            trace = cfg.get("trace")
            if isinstance(trace, str):
                trace = load_trace(trace)
            res = replay(cfg["agent"], trace, watch=cfg.get("watch"),
                         invariants=cfg.get("invariants"), label=cfg.get("label", "replay"))
        elif mode == "mine":
            spec = mine(cfg["agent"], cfg["good_tasks"], label=cfg.get("label", "mined"))
            spec.report()
            print("\nfaultline: mined %d rule(s) -> exit 0 (informational)" % len(spec.rules))
            _ci_emit("mine", 0, len(spec.rules))
            return 0
        else:
            print("faultline: unknown mode %r" % mode, file=sys.stderr)
            return 2
    except KeyError as exc:
        print("faultline: faultline_%s() is missing required key %s" % (mode, exc), file=sys.stderr)
        return 2

    res.report()
    breaks = len(res.breakers())
    checked = len(getattr(res, "rows", getattr(res, "findings", []))) or breaks
    _ci_emit(mode, breaks, checked)
    if breaks:
        print("\nfaultline: %d silent/broken finding(s) -> exit 1" % breaks)
        return 1
    print("\nfaultline: all checks held -> exit 0")
    return 0


def _run_doctor(target, task):
    """Drive `faultline doctor FILE.py:agent_fn` — preflight diagnosis, exit 1 if NOT READY."""
    if ":" not in target:
        print("faultline: doctor target must be FILE.py:agent_function "
              "(e.g. agent.py:my_agent)", file=sys.stderr)
        return 2
    path, fn_name = target.rsplit(":", 1)
    fn = _load_attr(path, fn_name)
    if fn is None:
        return 2
    from .doctor import doctor as _doctor
    try:
        rep = _doctor(fn, task)
    except Exception as exc:
        print("faultline: doctor failed — %s: %s" % (type(exc).__name__, exc), file=sys.stderr)
        return 2
    rep.report()
    return 0 if rep.ready else 1


MODE_COMMANDS = ("probe", "fuzz", "scenarios", "replay", "mine")

# Per-subcommand help — `faultline <cmd> --help` prints just that command's usage.
_SUBCOMMAND_HELP = {
    "scan": "faultline scan FILE.py:agent [--task '{...}'] [--explain]\n"
            "  Zero-config: discover the agent's wrapped tools, break them with the default fault\n"
            "  battery, gate CI (exit 1 on a silent failure). --task passes JSON (or a bare string)\n"
            "  to the agent; --explain shows exactly what was corrupted and why each FAIL.",
    "doctor": "faultline doctor FILE.py:agent [--task '{...}']\n"
              "  Preflight, no faults injected: reports whether faultline can test this agent — which\n"
              "  wrapped tools fire, action tools, return-type coverage gaps, async. Exit 1 if NOT READY.",
    "run": "faultline run FILE.py | config.json [--push]\n"
           "  Run a suite: a Python file defining faultline_suite(), or a declarative faultline.json.\n"
           "  Exit 1 on any silent failure or crash, so it gates CI. --push sends results to a dashboard.",
    "init": "faultline init\n"
            "  Scaffold faultline_suite.py + .github/workflows/faultline.yml in the current dir\n"
            "  (idempotent — never overwrites existing files).",
    "demo": "faultline demo\n  Run the built-in offline demo (a tiny broken agent, no API key).",
    "attest": "faultline attest FILE.py [--out faultline.report.json]\n"
              "  Run the suite AND write a tamper-evident report (run + an auditable evidence file).",
    "verify": "faultline verify REPORT.json\n"
              "  Re-derive the report's content hash and confirm it's untampered. Exit 1 if edited.",
    "probe": "faultline probe FILE.py\n  Run faultline_probe() — assert a property over edge inputs.",
    "fuzz": "faultline fuzz FILE.py\n  Run faultline_fuzz() — auto-generate edge inputs, find the breaker.",
    "scenarios": "faultline scenarios FILE.py\n  Run faultline_scenarios() — honest hard situations, no faults.",
    "replay": "faultline replay FILE.py\n  Run faultline_replay() — re-run a recorded trace, catch drift.",
    "mine": "faultline mine FILE.py\n  Run faultline_mine() — learn invariants from good runs, then enforce.",
}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "help"
    if cmd == "check":          # alias: check == run
        cmd = "run"
        argv = ["run"] + argv[1:]

    if cmd in ("version", "--version", "-V"):
        print("faultline %s" % __version__)
        return 0

    # `faultline <cmd> --help` -> just that subcommand's usage (not the whole wall of text).
    if cmd in _SUBCOMMAND_HELP and any(a in ("-h", "--help") for a in argv[1:]):
        print(_SUBCOMMAND_HELP[cmd])
        return 0

    if cmd == "demo":
        from .examples.quickstart import faultline_suite
        print("faultline demo -- a tiny offline agent, no API key needed\n")
        return _run_suite(faultline_suite(), _push=("--push" in argv))

    if cmd == "run":
        _push = "--push" in argv
        args = [a for a in argv[1:] if a != "--push"]
        if not args:
            print("faultline: 'run' needs a file, e.g. faultline run suite.py "
                  "(or a declarative faultline.json)", file=sys.stderr)
            return 2
        if args[0].endswith(".json"):
            from .config import load_config_suite
            try:
                suite = load_config_suite(args[0])
            except Exception as exc:  # noqa: BLE001
                print("faultline: bad config %s — %s: %s" % (args[0], type(exc).__name__, exc),
                      file=sys.stderr)
                return 2
        else:
            suite = _load_suite(args[0])
            if suite is None:
                return 2
        return _run_suite(suite, _push=_push)

    if cmd in ("scan", "doctor"):
        args = argv[1:]
        task = None
        target = None
        explain = False
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--explain":
                explain = True
                i += 1
                continue
            if a in ("--task", "-t"):
                if i + 1 >= len(args):
                    print("faultline: --task needs a value", file=sys.stderr)
                    return 2
                task = _parse_task(args[i + 1])
                i += 2
                continue
            if a.startswith("--task="):
                task = _parse_task(a.split("=", 1)[1])
                i += 1
                continue
            target = a
            i += 1
        if not target:
            print("faultline: '%s' needs an agent, e.g. "
                  "faultline %s agent.py:my_agent --task '{\"item\": \"widget\"}'"
                  % (cmd, cmd), file=sys.stderr)
            return 2
        return _run_doctor(target, task) if cmd == "doctor" else _run_scan(target, task, explain=explain)

    if cmd == "init":
        from .scaffold import init as _init
        created, skipped = _init(".")
        for p in created:
            print("  created  %s" % p)
        for p in skipped:
            print("  skipped  %s (already exists — left untouched)" % p)
        if created:
            print("\nNext: edit faultline_suite.py with your agent + wrapped tools, then run:")
            print("  faultline run faultline_suite.py")
        else:
            print("\nNothing to create — the suite and workflow already exist.")
        return 0

    if cmd == "attest":
        args = argv[1:]
        out_path = "faultline.report.json"
        positional = []
        i = 0
        while i < len(args):
            a = args[i]
            if a in ("--out", "-o"):
                if i + 1 >= len(args):
                    print("faultline: --out needs a path", file=sys.stderr)
                    return 2
                out_path = args[i + 1]
                i += 2
                continue
            if a.startswith("--out="):
                out_path = a.split("=", 1)[1]
                i += 1
                continue
            positional.append(a)
            i += 1
        if not positional:
            print("faultline: 'attest' needs a file, e.g. faultline attest suite.py", file=sys.stderr)
            return 2
        suite = _load_suite(positional[0])
        if suite is None:
            return 2
        return _run_attest(suite, out_path)

    if cmd == "verify":
        args = argv[1:]
        if not args:
            print("faultline: 'verify' needs a report, e.g. faultline verify faultline.report.json",
                  file=sys.stderr)
            return 2
        return _run_verify(args[0])

    if cmd in MODE_COMMANDS:
        if len(argv) < 2:
            print("faultline: '%s' needs a file, e.g. faultline %s suite.py" % (cmd, cmd), file=sys.stderr)
            return 2
        return _run_mode(cmd, argv[1])

    if cmd in ("help", "-h", "--help"):
        print(USAGE)
        return 0

    print("faultline: unknown command %r\n" % cmd, file=sys.stderr)
    print(USAGE, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
