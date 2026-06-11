# Contributing to faultline

Thanks for looking! faultline is a small, dependency-free Python tool, so the loop is fast.

## Setup & tests
No install needed to hack on it — it's pure standard library.

```bash
git clone https://github.com/aaravanmay/faultline && cd faultline
python3 tests/run_all.py        # the whole suite, deterministic, no API key. Must print "ALL GREEN ✓"
```

The framework-adapter suites (langgraph / langchain / llamaindex / pydantic-ai / crewai) skip cleanly on
Python 3.9 and run when those libs are installed on 3.10+. Everything else runs on 3.9.

## The one hard rule: Python 3.9 compatibility
faultline targets the macOS system Python **3.9.6**, so the core engine must stay 3.9-clean:
- `from __future__ import annotations` at the top of every module.
- **No** `X | Y` union syntax (use `Optional[X]` / `Union[...]`), **no** `match` statements.
- Keep the engine dependency-free. Optional integrations (pandas, the framework adapters) are detected by
  module name and must never become a hard import.

CI runs the suite on 3.9 / 3.11 / 3.12 — a 3.10+-only construct will go red on the 3.9 leg.

## Adding a fault
A fault corrupts a tool's return (or raises). Subclass `Fault` in `faultline/faults.py`:

```python
class MyFault(Fault):
    name = "my-fault"
    def hit(self, tool_name, args, kwargs, result):
        return <a corrupted version of result>     # or `raise` for a hard failure
    def reset(self):                                # only if you keep per-run state
        ...
```
Recurse into containers (dict/list/tuple) like `WrongNumber` does, and **pass non-matching types through
untouched** so it's never a silent no-op. Add a test that asserts the fault reaches a tool *and* doesn't on
a type it shouldn't touch.

## Adding an invariant
An invariant inspects a run and returns a **message string if violated, else `None`**:

```python
def my_rule(...):
    def inv(run):
        # run = {"events": [...tool calls...], "output": ..., "error": ...}
        if <violated>:
            return "what went wrong, in plain words"
        return None
    return inv
```
Be **low-false-positive**: return `None` on crash, empty output, and honest abstention. Add a both-direction
test (fires on the bad case, silent on the good one).

## Changing the detector — the benchmark gate
The zero-oracle detector (`faultline/detect.py`) is the moat. **Any change to detection logic must keep the
85-case benchmark at zero regression:**

```bash
for f in cases_action_agents cases_fn_traps cases_fp_traps cases_numeric_decisions cases_real_world; do
  PYTHONPATH=. python3 benchmark/$f.py; done    # expect 40 FAIL / 45 PASS, unchanged
```
If a case flips, that's a regression — explain it or revert. Don't retrofit the frozen benchmark to make a
change pass; that's the dishonest move. See `benchmark/MEASUREMENT.md` and `CAPABILITIES.md`.

## Pull requests
- One change per PR, with a test that fails before and passes after.
- Run `python3 tests/run_all.py` (and the benchmark if you touched the detector) before pushing.
- Keep the honesty bar: no overclaiming in docs, and the 85-case benchmark numbers are never attached to
  LLM-agent or framework claims (`CAPABILITIES.md` is the guardrail).
