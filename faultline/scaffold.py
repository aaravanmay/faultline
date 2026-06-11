"""faultline init — scaffold a starter suite + CI workflow into a repo (never overwrites)."""
from __future__ import annotations

import os

_SUITE_STUB = '''\
"""Your faultline suite. Run:  faultline run faultline_suite.py
(exit code 1 = a silent failure was found, so this gates CI out of the box.)
"""
import faultline as fl


# 1. Wrap your real tools so faultline can break their returns.
@fl.tool
def get_data(key):
    # TODO: replace with your real tool. Return whatever it really returns.
    return {"key": key, "value": 100}


# 2. Your agent: agent(task) -> output. It calls your wrapped tools.
def agent(task):
    data = get_data(task.get("key", "example"))   # .get so `faultline doctor` works with no --task
    # TODO: your real agent logic — the decision/action that depends on the tool's value.
    return {"answer": data["value"]}


# 3. (Optional) an invariant: a rule that must always hold. Return a message if violated, else None.
def my_rule(run):
    # `run` = {"events": [...tool calls...], "output": ..., "error": ...}
    # TODO: e.g. refuse to act on an out-of-range value. Return None means "this run is fine."
    return None


# Note: out of the box this starter agent passes the tool's value straight through with no guard,
# so `faultline run` will CATCH it acting on corrupted data and exit 1 — that's faultline working.
# Add a sanity-check (or an invariant above) so the agent refuses bad data, and the run goes green.
def faultline_suite():
    return {
        "agent": agent,
        "task": {"key": "example"},
        # faultline breaks each tool's return with these and checks what your agent does:
        "faults": [fl.WrongNumber(), fl.StaleData(), fl.EmptyResult(), fl.NullResponse()],
        "invariants": [my_rule],
        "trials": 3,
    }
'''

_CI_STUB = '''\
name: faultline
on: [push, pull_request]

jobs:
  faultline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install faultline
      - run: faultline run faultline_suite.py
'''


def init(target_dir="."):
    """Write faultline_suite.py + .github/workflows/faultline.yml into target_dir.

    Idempotent and SAFE: never overwrites an existing file. Returns (created, skipped) path lists.
    """
    created, skipped = [], []

    suite_path = os.path.join(target_dir, "faultline_suite.py")
    if os.path.exists(suite_path):
        skipped.append(suite_path)
    else:
        with open(suite_path, "w") as f:
            f.write(_SUITE_STUB)
        created.append(suite_path)

    wf_dir = os.path.join(target_dir, ".github", "workflows")
    wf_path = os.path.join(wf_dir, "faultline.yml")
    if os.path.exists(wf_path):
        skipped.append(wf_path)
    else:
        os.makedirs(wf_dir, exist_ok=True)
        with open(wf_path, "w") as f:
            f.write(_CI_STUB)
        created.append(wf_path)

    return created, skipped
