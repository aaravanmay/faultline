"""Load a declarative `faultline.json` config into a suite dict — `faultline run faultline.json`.

JSON (not YAML/TOML) on purpose: faultline's engine is dependency-free and targets Python 3.9, which
has no `tomllib` and we won't pull in PyYAML. The fault TYPES are a closed allowlist (no eval, ever);
the agent + invariants are module references (`file.py:name`), loaded like the Python suite path.

    {
      "agent": "my_agent.py:agent",
      "task": {"sku": "A-12"},
      "faults": [
        {"type": "WrongNumber", "factor": 5, "targets": ["get_price"]},
        "EmptyResult",
        {"type": "Timeout"}
      ],
      "invariants": ["my_agent.py:my_rule"],
      "trials": 3
    }
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

from . import faults as _faults

# Closed allowlist — a config can only name a built-in fault, never run arbitrary code.
_FAULT_ALLOWLIST = {
    "WrongNumber": _faults.WrongNumber,
    "StaleData": _faults.StaleData,
    "Truncate": _faults.Truncate,
    "NullResponse": _faults.NullResponse,
    "EmptyResult": _faults.EmptyResult,
    "Timeout": _faults.Timeout,
    "ServerError": _faults.ServerError,
}


def _load_ref(ref):
    """Load `FILE.py:attr` -> the object (the agent or an invariant)."""
    if ":" not in ref:
        raise ValueError("expected FILE.py:name, got %r" % ref)
    path, attr = ref.rsplit(":", 1)
    if not os.path.exists(path):
        raise ValueError("no such file: %s" % path)
    spec = importlib.util.spec_from_file_location("_faultline_cfg_mod", path)
    mod = importlib.util.module_from_spec(spec)
    sys.path.insert(0, os.path.dirname(os.path.abspath(path)))
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    obj = getattr(mod, attr, None)
    if obj is None:
        raise ValueError("%s defines no %s" % (path, attr))
    return obj


def _build_fault(spec):
    if isinstance(spec, str):
        spec = {"type": spec}
    if not isinstance(spec, dict) or "type" not in spec:
        raise ValueError("each fault must be a name or an object with a 'type', got %r" % (spec,))
    cls = _FAULT_ALLOWLIST.get(spec["type"])
    if cls is None:
        raise ValueError("unknown fault type %r (allowed: %s)"
                         % (spec["type"], ", ".join(sorted(_FAULT_ALLOWLIST))))
    kwargs = {k: v for k, v in spec.items() if k != "type"}
    return cls(**kwargs)


def load_config_suite(path):
    """Parse a faultline.json config into the suite dict that check()/`faultline run` consume."""
    with open(path) as f:
        cfg = json.load(f)
    if "agent" not in cfg:
        raise ValueError("config needs an \"agent\": \"FILE.py:fn\"")
    return {
        "agent": _load_ref(cfg["agent"]),
        "task": cfg.get("task"),
        "faults": [_build_fault(s) for s in cfg.get("faults", [])],
        "invariants": [_load_ref(r) for r in cfg.get("invariants", [])],
        "trials": cfg.get("trials", 5),
    }
