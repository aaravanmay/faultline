"""Wave-3 detector upgrades — tests for all four jobs. Deterministic, no API.

1. Display-only vs consequential action-arg divergence (both directions).
2. Derived-value layer: catches arithmetic/count-transformed corruption, and
   does NOT flag near-misses (clamped outputs, untraceable divergence).
3. WrongNumber on pandas DataFrames/Series (skips gracefully without pandas).
4. Dict mutators in fuzz._default_mutators.

Run:  python3 tests/test_wave3_detector.py   (expects all passed).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faultline as fl
from faultline.faults import WrongNumber
from faultline.fuzz import _default_mutators

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("  ok  " if cond else "FAIL  ") + name)


# ===========================================================================
# 1. Display-only vs consequential action-arg divergence
# ===========================================================================

# --- 1a. SAME action, corrupted value rides along ONLY in a display arg -> PASS
def _case_display_only():
    @fl.tool
    def get_discount_w3a(item):
        return 10

    def _order_w3a(item, qty, display_discount):
        return {"ok": True}

    order_w3a = fl.wrap(_order_w3a, is_action=True)

    def agent(task):
        d = get_discount_w3a(task["item"])
        return order_w3a(task["item"], task["qty"], d)

    return fl.check(agent, {"item": "laptop", "qty": 2},
                    faults=[fl.WrongNumber(factor=5.0, targets=["get_discount_w3a"])],
                    invariants=[], trials=3)


_r = _case_display_only()
check("display-only arg divergence is NOT flagged", _r.rows[0]["verdict"] == "PASS")


# --- 1b. SAME action but the corrupted value lands in a CONSEQUENTIAL arg -> FAIL
def _case_consequential():
    @fl.tool
    def get_qty_w3b(item):
        return 12

    def _order_w3b(item, qty, display_discount):
        return {"ok": True}

    order_w3b = fl.wrap(_order_w3b, is_action=True)

    def agent(task):
        q = get_qty_w3b(task["item"])
        return order_w3b(task["item"], q, 10)

    return fl.check(agent, {"item": "laptop"},
                    faults=[fl.WrongNumber(factor=5.0, targets=["get_qty_w3b"])],
                    invariants=[], trials=3)


_r = _case_consequential()
check("consequential arg divergence (qty) IS flagged", _r.rows[0]["verdict"] == "FAIL")


# --- 1c. NEW action under fault (no baseline call) -> always flagged, even if
#         its only args are display-named.
def _case_new_action_display_named():
    @fl.tool
    def get_metric_w3c(name):
        return 20

    def _send_alert_w3c(message):
        return {"sent": True}

    send_alert_w3c = fl.wrap(_send_alert_w3c, is_action=True)

    def agent(task):
        v = get_metric_w3c(task["metric"])
        if v > 50:
            return send_alert_w3c("metric is %s" % v)
        return {"decision": "NO_ALERT"}

    return fl.check(agent, {"metric": "err_rate"},
                    faults=[fl.WrongNumber(factor=5.0, targets=["get_metric_w3c"])],
                    invariants=[], trials=3)


_r = _case_new_action_display_named()
check("NEW action with display-named arg IS still flagged",
      _r.rows[0]["verdict"] == "FAIL")


# --- 1d. SAME action, corrupted value embedded in a display-named STRING arg -> PASS,
#         but in a consequential string arg (address) -> FAIL.
def _case_string_args(param_is_display):
    @fl.tool
    def get_eta_w3d(order_id):
        return 12  # minutes

    if param_is_display:
        def _dispatch(order_id, log_message):
            return {"ok": True}
    else:
        def _dispatch(order_id, address):
            return {"ok": True}

    dispatch = fl.wrap(_dispatch, is_action=True, name="dispatch_w3d_%s" % param_is_display)

    def agent(task):
        eta = get_eta_w3d(task["order_id"])
        return dispatch(task["order_id"], "ETA %s minutes" % eta)

    return fl.check(agent, {"order_id": "ORD-1"},
                    faults=[fl.WrongNumber(factor=5.0, targets=["get_eta_w3d"])],
                    invariants=[], trials=3)


check("corruption inside a log_message string arg is NOT flagged",
      _case_string_args(True).rows[0]["verdict"] == "PASS")
check("corruption inside an address string arg IS flagged",
      _case_string_args(False).rows[0]["verdict"] == "FAIL")


# ===========================================================================
# 2. Derived-value layer
# ===========================================================================

# --- 2a. Arithmetic transform: only income * rate reaches the output; the
#         action takes an opaque reference id. Ratio lockstep must catch it.
def _case_derived_tax():
    @fl.tool
    def get_income_w3e(taxpayer):
        return 50000

    def _file_return(ref_id):
        return {"filed": True}

    file_return = fl.wrap(_file_return, is_action=True)

    def agent(task):
        income = get_income_w3e(task["taxpayer"])
        tax_due = round(income * 0.22, 2)
        file_return(task["ref"])
        return {"tax_due": tax_due}

    return fl.check(agent, {"taxpayer": "T1", "ref": "REF9"},
                    faults=[fl.WrongNumber(factor=5.0, targets=["get_income_w3e"])],
                    invariants=[], trials=3)


_r = _case_derived_tax()
check("derived value (income*rate) IS caught", _r.rows[0]["verdict"] == "FAIL")
check("derived catch reports lockstep detail", "lockstep" in _r.rows[0]["detail"])


# --- 2b. Count transform: truncated list -> count in prose output; action takes
#         only a batch id. Count identity must catch it.
def _case_derived_count():
    @fl.tool
    def fetch_jobs_w3f(queue):
        return [{"id": i} for i in range(6)]

    def _schedule(batch_id):
        return {"ok": True}

    schedule = fl.wrap(_schedule, is_action=True)

    def agent(task):
        jobs = fetch_jobs_w3f(task["queue"])
        schedule(task["batch"])
        return "queued %d jobs" % len(jobs)

    return fl.check(agent, {"queue": "main", "batch": "B1"},
                    faults=[fl.Truncate(targets=["fetch_jobs_w3f"])],
                    invariants=[], trials=3)


_r = _case_derived_count()
check("derived count (truncated list -> prose count) IS caught",
      _r.rows[0]["verdict"] == "FAIL")


# --- 2c. NEAR-MISS that must NOT flag: output number changes under fault, but
#         via a clamp — the divergence is NOT in lockstep with the corruption.
def _case_near_miss_clamp():
    @fl.tool
    def get_stock_w3g(item):
        return 16

    def agent(task):
        stock = get_stock_w3g(task["item"])
        risk = max(0.0, (1.0 - min(stock, 20) / 20.0) * 100.0)
        return {"risk": round(risk, 1), "action": "monitor"}

    return fl.check(agent, {"item": "x"},
                    faults=[fl.WrongNumber(factor=5.0, targets=["get_stock_w3g"])],
                    invariants=[], trials=3)


_r = _case_near_miss_clamp()
check("clamped (untraceable) numeric divergence is NOT flagged",
      _r.rows[0]["verdict"] == "PASS")


# --- 2d. Rejection language suppresses the derived layer (good logging is not
#         a silent failure).
def _case_derived_with_rejection():
    @fl.tool
    def get_income_w3h(taxpayer):
        return 50000

    def agent(task):
        income = get_income_w3h(task["taxpayer"])
        tax_due = round(income * 0.22, 2)
        if tax_due > 20000:
            return {"abstain": True, "computed": tax_due,
                    "reason": "implausible income — refusing to file"}
        return {"tax_due": tax_due}

    return fl.check(agent, {"taxpayer": "T1"},
                    faults=[fl.WrongNumber(factor=5.0, targets=["get_income_w3h"])],
                    invariants=[], trials=3)


_r = _case_derived_with_rejection()
check("derived layer is suppressed when the agent rejects the value",
      _r.rows[0]["verdict"] == "PASS")


# ===========================================================================
# 3. WrongNumber on pandas DataFrames / Series (optional dependency)
# ===========================================================================

try:
    import pandas as pd
    _HAVE_PANDAS = True
except ImportError:
    _HAVE_PANDAS = False

if _HAVE_PANDAS:
    _df = pd.DataFrame({
        "price": [10.0, 0.0, -3.5],
        "qty": [2, 7, 0],
        "ticker": ["AAPL", "MSFT", "NVDA"],
        "active": [True, False, True],
    })
    _orig = _df.copy(deep=True)
    _wn = WrongNumber(factor=5.0)
    _out = _wn._corrupt(_df)

    check("pandas: float column bent x5", list(_out["price"]) == [50.0, 5.0, -17.5])
    check("pandas: int column bent x5", list(_out["qty"]) == [10, 35, 5])
    check("pandas: string column untouched", list(_out["ticker"]) == ["AAPL", "MSFT", "NVDA"])
    check("pandas: bool column untouched", list(_out["active"]) == [True, False, True])
    check("pandas: caller's DataFrame NOT mutated", _df.equals(_orig))

    _s = pd.Series([1.0, 2.0, 0.0], name="vals")
    _s_orig = _s.copy(deep=True)
    _s_out = _wn._corrupt(_s)
    check("pandas: Series bent x5 (0 -> factor)", list(_s_out) == [5.0, 10.0, 5.0])
    check("pandas: caller's Series NOT mutated", _s.equals(_s_orig))

    _obj = pd.Series(["a", "b"])
    check("pandas: non-numeric Series passes through unchanged",
          list(_wn._corrupt(_obj)) == ["a", "b"])

    # end-to-end: a tool returning a DataFrame, agent derives a sum from it
    @fl.tool
    def get_frame_w3i(q):
        return pd.DataFrame({"v": [10.0, 20.0]})

    def agent_w3i(task):
        df = get_frame_w3i(task["q"])
        return {"total": float(df["v"].sum())}

    _r = fl.check(agent_w3i, {"q": 1},
                  faults=[fl.WrongNumber(factor=5.0, targets=["get_frame_w3i"])],
                  invariants=[], trials=3)
    check("pandas: end-to-end DataFrame corruption flows and is flagged",
          _r.rows[0]["verdict"] == "FAIL")
else:
    print("  skip pandas tests (pandas not installed) — feature degrades gracefully")
    # The degradation contract still holds without pandas: _corrupt must not
    # blow up on ordinary values and the module must import with zero pandas cost.
    _wn = WrongNumber(factor=5.0)
    check("no-pandas: plain values still corrupt fine", _wn._corrupt(2) == 10)


# ===========================================================================
# 4. Dict mutators in fuzz
# ===========================================================================

_muts = _default_mutators({"a": 1})
_names = [n for n, _ in _muts]
check("fuzz: dict base routes to dict mutators",
      "empty-dict" in _names and "drop-first-key" in _names
      and "none-first-key" in _names and "bend-numerics" in _names
      and "extra-unexpected-key" in _names)

_base = {"user": "u1", "amount": 50, "meta": {"retries": 2}}


def _mut_by_name(name):
    for n, m in _muts:
        if n == name:
            return m
    return None


check("fuzz: empty-dict mutator", _mut_by_name("empty-dict")(_base) == {})
check("fuzz: drop-first-key removes exactly the first key",
      _mut_by_name("drop-first-key")(_base) == {"amount": 50, "meta": {"retries": 2}})
check("fuzz: none-first-key nulls exactly the first key",
      _mut_by_name("none-first-key")(_base)["user"] is None)
_bent = _mut_by_name("bend-numerics")(_base)
check("fuzz: bend-numerics bends top-level numerics", _bent["amount"] == 50000)
check("fuzz: bend-numerics recurses one level into nested dicts",
      _bent["meta"]["retries"] == 2000)
check("fuzz: extra-unexpected-key adds a key",
      "_faultline_unexpected" in _mut_by_name("extra-unexpected-key")(_base))
check("fuzz: mutators never mutate the base dict",
      _base == {"user": "u1", "amount": 50, "meta": {"retries": 2}})


# end-to-end: fuzz() with a dict base discovers a planted breaker
def _lookup(cfg):
    # planted bug: silently returns 0 when 'amount' is missing or None
    amt = cfg.get("amount") if isinstance(cfg, dict) else None
    return 0 if amt is None else amt * 2


def _prop_nonzero(inp, out, err):
    if err is None and out == 0:
        return "silently returned 0"
    return None


_f1 = fl.fuzz(_lookup, {"user": "u1", "amount": 50}, [_prop_nonzero], label="dict-fuzz")
_f2 = fl.fuzz(_lookup, {"user": "u1", "amount": 50}, [_prop_nonzero], label="dict-fuzz")
check("fuzz: dict base discovers the planted breaker", len(_f1.breakers()) >= 1)
check("fuzz: dict fuzzing is deterministic across runs",
      [(r["case"], r["status"]) for r in _f1.rows] == [(r["case"], r["status"]) for r in _f2.rows])


passed = sum(1 for _, c in results if c)
print("\n%d passed, %d failed" % (passed, len(results) - passed))
sys.exit(0 if passed == len(results) else 1)
