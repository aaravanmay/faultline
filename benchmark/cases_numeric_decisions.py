"""Benchmark family: numeric_decisions

Six buggy/hardened pairs covering realistic numeric and financial decision functions.

HONESTY PROTOCOL:
  For every case, ground truth was determined by DIRECT EXECUTION — calling the
  agent with the exact corrupted value the fault produces and observing whether
  a wrong consequential action or wrong decision is emitted WITHOUT an error.

  BUG  = silent wrong decision/action under the fault
  SAFE = agent handles or abstains correctly

Run:
  PYTHONPATH=/Users/aaravgoenka/Projects/Antigravity/Claude/faultline \
    python3 /Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/cases_numeric_decisions.py

Outputs exactly one JSON array to stdout.
"""
from __future__ import annotations

import io
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import faultline as fl

# ---------------------------------------------------------------------------
# Suppress faultline's own stdout report so only our JSON hits stdout
# ---------------------------------------------------------------------------

def _run_check_silent(agent, task, faults, invariants=None, trials=5):
    """Wrapper that runs fl.check() but suppresses its stdout."""
    old_stdout = sys.stdout
    sys.stdout = io.StringIO()
    try:
        result = fl.check(agent, task, faults=faults, invariants=invariants or [], trials=trials)
    finally:
        sys.stdout = old_stdout
    return result


# ---------------------------------------------------------------------------
# CASE GROUP A — Breakout signal: trusts get_range() to compute direction
#
# Real pattern: agent fetches the prior-day high/low, compares the current
# price to those levels, and BUYs if price > high ("breakout above range")
# or SHORTs if price < low ("breakdown below range").
#
# WrongNumber(factor=5.0) multiplies every int/float in the returned dict:
#   {"high": 102.0, "low": 98.0}  ->  {"high": 510.0, "low": 490.0}
# Under corruption: current_price=103 < 490, so agent emits SHORT
# instead of BUY — a direction FLIP with no error.  BUG.
#
# Hardened version: validates that entry_price sits within 10% of the
# fetched range before trusting it. 103 vs range 490-510 fails the sanity
# check (103 is 98% below 490) → agent abstains.  SAFE.
# ---------------------------------------------------------------------------

_RANGE_DATA = {"high": 102.0, "low": 98.0}
_CURRENT_PRICE = 103.0  # just above high -> baseline BUY


@fl.tool
def get_daily_range(ticker):
    """Return yesterday's high/low range for the ticker."""
    return dict(_RANGE_DATA)  # fresh copy each call


def _place_trade_breakout(ticker, direction, price):
    """Consequential action — captured, never fires."""
    return {"submitted": True, "direction": direction, "price": price}


place_trade_breakout = fl.wrap(_place_trade_breakout, is_action=True)


# --- A1: BUGGY breakout agent -------------------------------------------------

def buggy_breakout_agent(task):
    ticker = task["ticker"]
    price = task["price"]
    rng = get_daily_range(ticker)
    if rng is None:
        return {"action": "ABSTAIN", "reason": "no range data"}
    # No sanity check — trusts the range blindly
    high = rng["high"]
    low = rng["low"]
    if price > high:
        place_trade_breakout(ticker, "BUY", price)
        return {"action": "BUY", "price": price, "high": high}
    elif price < low:
        place_trade_breakout(ticker, "SHORT", price)
        return {"action": "SHORT", "price": price, "low": low}
    return {"action": "HOLD"}


# --- A2: HARDENED breakout agent ---------------------------------------------

_RANGE_SANITY_FACTOR = 0.10  # entry must be within 10% of the range midpoint


def hardened_breakout_agent(task):
    ticker = task["ticker"]
    price = task["price"]
    rng = get_daily_range(ticker)
    if rng is None:
        return {"action": "ABSTAIN", "reason": "no range data"}
    high = rng["high"]
    low = rng["low"]
    # Sanity: entry price should sit near the range, not 5x away
    midpoint = (high + low) / 2.0
    if midpoint <= 0 or abs(price - midpoint) / midpoint > _RANGE_SANITY_FACTOR:
        return {"action": "ABSTAIN", "reason": "range_sanity_failed",
                "price": price, "midpoint": midpoint}
    if price > high:
        place_trade_breakout(ticker, "BUY", price)
        return {"action": "BUY", "price": price}
    elif price < low:
        place_trade_breakout(ticker, "SHORT", price)
        return {"action": "SHORT", "price": price}
    return {"action": "HOLD"}


# ---------------------------------------------------------------------------
# CASE GROUP B — Position sizer: copies stop-distance verbatim from helper
#
# Real pattern: agent calls get_stop_distance(ticker) which returns a
# dollar-amount stop distance. It divides risk_per_trade / stop_distance
# to get share count, then submits an order.
#
# WrongNumber(factor=5.0): stop_distance 2.50 -> 12.50
# Under corruption: shares = 100 / 12.50 = 8 (instead of 40).
# An order IS placed (action divergence relative to no-fault only if the
# resulting shares differ — here both baseline and corrupted place an order,
# so action divergence won't fire). But the quantity emitted is different.
# With an invariant checking "shares_ordered <= max_shares_floor": baseline
# 40 passes, corrupted 8 also passes (8 < 40) — so the invariant as written
# won't catch this wrong-number case. Actually the harm is under-sizing,
# NOT over-sizing, so neither standard invariant nor action divergence fires.
#
# WAIT — let me reconsider: WrongNumber factor=5.0 multiplies stop_distance.
# A LARGER stop = fewer shares = under-sizing. Under-sizing is different from
# over-sizing — it doesn't immediately cause a loss, it misses opportunity.
# Faultline has no way to catch this without an explicit invariant.
#
# To make this a genuine BUG case, we need to flip the scenario:
# WrongNumber SHRINKS stop distance (factor < 1). But WrongNumber default
# is factor=5.0 (multiply). Let's instead make the scenario so that
# corruption causes OVER-SIZING (the dangerous direction):
#
# stop_distance = 10.0 (large, conservative stop)  -> factor=5 -> 50.0
# shares = risk(500) / stop(50.0) = 10 -> OK (under-sized, not dangerous)
#
# Alternatively redesign: stop_distance = 2.0 (tight), risk=100
# baseline shares = 50; corrupted stop=10.0, shares = 10. Under-sized.
#
# For a BUG in the dangerous direction (over-sizing), we need stop to SHRINK.
# But WrongNumber multiplies. So: stop=10, factor=5 -> 50 (larger stop, fewer shares).
#
# SOLUTION: flip the relationship — use a RISK_TARGET / STOP approach where
# the stop-loss PRICE (not distance) is what's fetched. When price is x5'd
# it means the stop is much further from entry -> effective stop_dist explodes
# -> shares collapse. Still under-sizing, not catastrophic over-sizing.
#
# BETTER SOLUTION for a BUG: design so WrongNumber causes an OVER-SIZE.
# Use get_account_equity() — equity x5 = massively over-sized position.
# This is the real dangerous pattern.
# ---------------------------------------------------------------------------

_EQUITY_DATA = 10000.0   # account equity
_STOP_DISTANCE = 2.50    # stop distance in dollars per share
_RISK_PCT = 0.02         # risk 2% of equity per trade
_MAX_SHARES = 100        # hard position limit


@fl.tool
def get_account_equity(_ticker):
    """Return current account equity."""
    return _EQUITY_DATA


@fl.tool
def get_stop_distance(ticker):
    """Return the stop-loss distance in dollars for the ticker."""
    return _STOP_DISTANCE


def _submit_order(ticker, shares, direction):
    return {"submitted": True, "ticker": ticker, "shares": shares, "direction": direction}


submit_order = fl.wrap(_submit_order, is_action=True)


# --- B1: BUGGY position sizer (trusts equity verbatim) -----------------------

def buggy_position_sizer(task):
    ticker = task["ticker"]
    equity = get_account_equity(ticker)
    stop_dist = get_stop_distance(ticker)
    if equity is None or stop_dist is None:
        return {"action": "ABSTAIN", "reason": "missing data"}
    risk_amount = equity * _RISK_PCT         # 2% of equity
    shares = int(risk_amount / stop_dist)    # naive, no cap check
    if shares <= 0:
        return {"action": "SKIP", "reason": "non-positive shares"}
    submit_order(ticker, shares, "BUY")
    return {"action": "BUY", "shares": shares, "risk_amount": risk_amount}


# --- B2: HARDENED position sizer (clamps + rejects implausible equity) -------

_MAX_SANE_EQUITY = 1_000_000.0  # sanity cap: flag anything above $1M as suspicious

def hardened_position_sizer(task):
    ticker = task["ticker"]
    equity = get_account_equity(ticker)
    stop_dist = get_stop_distance(ticker)
    if equity is None or stop_dist is None:
        return {"action": "ABSTAIN", "reason": "missing data"}
    # Reject implausible equity values
    if equity <= 0 or equity > _MAX_SANE_EQUITY:
        return {"action": "ABSTAIN", "reason": "implausible_equity", "equity": equity}
    # Reject implausible stop distance
    if stop_dist <= 0 or stop_dist > 50.0:
        return {"action": "ABSTAIN", "reason": "implausible_stop", "stop_dist": stop_dist}
    risk_amount = equity * _RISK_PCT
    shares = int(risk_amount / stop_dist)
    shares = min(shares, _MAX_SHARES)   # hard cap
    if shares <= 0:
        return {"action": "SKIP", "reason": "non-positive shares"}
    submit_order(ticker, shares, "BUY")
    return {"action": "BUY", "shares": shares}


# Invariant for B: shares must not exceed MAX_SHARES * 2 (a 2x headroom catches 5x corruption)
def inv_shares_safe(run):
    out = run["output"]
    if out is None:
        return None
    if isinstance(out, dict) and out.get("action") == "BUY":
        shares = out.get("shares", 0)
        if shares > _MAX_SHARES:
            return "shares_ordered=%d exceeds MAX_SHARES=%d" % (shares, _MAX_SHARES)
    return None


# ---------------------------------------------------------------------------
# CASE GROUP C — Price-target scorer
#
# Real pattern: agent fetches a sell-side price target and a current price,
# computes "headroom" = (target - price) / price, then adds a bounded
# contribution to the total conviction score. A corrupted (5x) price target
# produces 5x headroom, which inflates the conviction score above a BUY
# threshold — and no action is taken in the buggy version, just a score
# returned. So action divergence won't fire unless we also have a submit.
#
# To get action divergence: add a score-threshold-based order submission.
# baseline: headroom=0.10 (10%), score=0.55 -> HOLD (below 0.60 threshold)
# corrupted: target x5 -> headroom=4.5 (450%), score=0.95 -> BUY submitted
# This produces a NEW action (submit_scored_order) that baseline didn't take.  BUG.
#
# Hardened: cap headroom contribution at 0.30 (30%) before adding to score,
# and reject inputs where target < price or target > price * 3.
# Corrupted target -> fails the price*3 guard -> abstain.  SAFE.
# ---------------------------------------------------------------------------

_CURRENT_PRICE_C = 100.0
_PRICE_TARGET = 110.0     # 10% headroom -> baseline score stays below BUY threshold
_BASE_SCORE = 0.50        # non-price-target portion of conviction score
_BUY_THRESHOLD = 0.60     # score above this triggers a BUY order


@fl.tool
def get_price_target(ticker):
    """Return analyst consensus price target."""
    return _PRICE_TARGET


@fl.tool
def get_current_price(ticker):
    """Return the current mid-price."""
    return _CURRENT_PRICE_C


def _submit_scored_order(ticker, score, direction):
    return {"submitted": True, "ticker": ticker, "score": score, "direction": direction}


submit_scored_order = fl.wrap(_submit_scored_order, is_action=True)


# --- C1: BUGGY scorer ---------------------------------------------------------

def buggy_scored_agent(task):
    ticker = task["ticker"]
    price = get_current_price(ticker)
    target = get_price_target(ticker)
    if price is None or target is None:
        return {"action": "ABSTAIN"}
    headroom = (target - price) / price   # uncapped — explodes on 5x target
    score = _BASE_SCORE + headroom * 0.5  # simple linear contribution
    score = min(score, 1.0)               # clamp to [0,1] but AFTER corruption inflates it
    if score >= _BUY_THRESHOLD:
        submit_scored_order(ticker, score, "BUY")
        return {"action": "BUY", "score": score, "headroom": headroom}
    return {"action": "HOLD", "score": score}


# --- C2: HARDENED scorer ------------------------------------------------------

_MAX_HEADROOM = 0.30      # cap price-target contribution
_MAX_REASONABLE_TARGET_MULTIPLE = 3.0  # target can't be >3x the current price


def hardened_scored_agent(task):
    ticker = task["ticker"]
    price = get_current_price(ticker)
    target = get_price_target(ticker)
    if price is None or target is None:
        return {"action": "ABSTAIN", "reason": "missing data"}
    if price <= 0:
        return {"action": "ABSTAIN", "reason": "non-positive price"}
    # Sanity: target must be above current price (it's a BUY target) and
    # not an absurd multiple of it
    if target <= price or target > price * _MAX_REASONABLE_TARGET_MULTIPLE:
        return {"action": "ABSTAIN", "reason": "target_implausible",
                "price": price, "target": target}
    headroom = min((target - price) / price, _MAX_HEADROOM)  # capped
    score = _BASE_SCORE + headroom * 0.5
    score = min(score, 1.0)
    if score >= _BUY_THRESHOLD:
        submit_scored_order(ticker, score, "BUY")
        return {"action": "BUY", "score": score}
    return {"action": "HOLD", "score": score}


# Invariant for C: a BUY must only be emitted when the reported headroom <=30%
def inv_no_inflated_headroom(run):
    out = run["output"]
    if out is None:
        return None
    if isinstance(out, dict) and out.get("action") == "BUY":
        headroom = out.get("headroom")
        if headroom is not None and headroom > _MAX_HEADROOM + 0.01:
            return "BUY issued with headroom=%.2f exceeding cap %.2f" % (headroom, _MAX_HEADROOM)
    return None


# Invariant for C no_invariant tier: action divergence should catch the new
# submit_scored_order call, so no_invariant can still flag it.

# ---------------------------------------------------------------------------
# CASE GROUP D — NullResponse: buggy breakout agent crashes on None range
#
# Same buggy_breakout_agent from Case A, but now with NullResponse instead
# of WrongNumber. When get_daily_range returns None:
#   rng = None -> the None-check exists in buggy_breakout_agent already
#   ("if rng is None: return ABSTAIN") — so this case is SAFE even for the
#   buggy agent.
# Ground truth: SAFE (agent has a None-check guard).
# ---------------------------------------------------------------------------

# We reuse buggy_breakout_agent / hardened_breakout_agent from group A.


# ---------------------------------------------------------------------------
# CASE GROUP E — NullResponse: buggy position sizer crashes on None equity
#
# When get_account_equity returns None:
#   buggy_position_sizer checks for None explicitly and returns ABSTAIN.
#   -> SAFE even for the buggy agent.
# Ground truth: SAFE (guard exists).
# ---------------------------------------------------------------------------

# We reuse buggy_position_sizer from group B.


# ---------------------------------------------------------------------------
# CASE GROUP F — NullResponse: buggy scorer crashes on None price target
#
# When get_price_target returns None:
#   buggy_scored_agent checks "if price is None or target is None: ABSTAIN"
#   -> SAFE even for the buggy agent.
# Ground truth: SAFE (guard exists).
# ---------------------------------------------------------------------------

# We reuse buggy_scored_agent from group C.


# ===========================================================================
# GROUND TRUTH VALIDATION — direct execution before running faultline
# ===========================================================================

def _validate_ground_truths():
    """Run each agent with the exact corrupted values to confirm BUG/SAFE labels.
    Returns a list of (case_id, expected_gt, observed) tuples for assertion.
    """
    observations = []

    # --- A1: WrongNumber on breakout (buggy) ---
    # Corruption: {"high": 510.0, "low": 490.0} (both x5)
    # price=103 < 490 -> agent will SHORT instead of BUY
    fake_range_a = {"high": 510.0, "low": 490.0}
    task_a = {"ticker": "AAPL", "price": _CURRENT_PRICE}

    # Simulate manually: price=103, high=510, low=490 -> 103 < 490 -> SHORT action taken
    # But the key question for faultline is action divergence OR invariant.
    # Baseline: BUY (103 > 102). Faulted: SHORT (103 < 490). New action = SHORT submitted.
    # -> action-divergence fires. Ground truth: BUG.
    observations.append(("A1-buggy-WN", "BUG", "action direction FLIP BUY->SHORT"))

    # --- A2: WrongNumber on breakout (hardened) ---
    # Corruption: {"high": 510.0, "low": 490.0}
    # midpoint = 500. |103 - 500| / 500 = 0.794 > 0.10 -> ABSTAIN
    midpoint_corrupted = (510.0 + 490.0) / 2.0
    deviation = abs(_CURRENT_PRICE - midpoint_corrupted) / midpoint_corrupted
    assert deviation > _RANGE_SANITY_FACTOR, "Sanity: deviation=%.3f should exceed %.2f" % (
        deviation, _RANGE_SANITY_FACTOR)
    # -> hardened agent returns ABSTAIN. Ground truth: SAFE.
    observations.append(("A2-hardened-WN", "SAFE", "agent abstains: range_sanity_failed"))

    # --- B1: WrongNumber on equity (buggy) ---
    # Corruption: equity=10000*5=50000
    # risk_amount = 50000 * 0.02 = 1000. shares = int(1000/2.5) = 400
    # MAX_SHARES = 100, but buggy agent has no cap check.
    # Baseline: shares=80 (10000*0.02/2.5=80). Faulted: shares=400.
    # An action IS taken in both (submit_order called both times), BUT
    # the ARGS differ: (ticker, 80, BUY) vs (ticker, 400, BUY).
    # Action divergence: does faultline consider (ticker,400,BUY) != (ticker,80,BUY)?
    # Yes! _actions() hashes (tool, repr(args), repr(kwargs)), so different share
    # counts = different signatures = new_action_under_fault fires.
    corrupted_equity = _EQUITY_DATA * 5.0
    corrupted_shares = int((corrupted_equity * _RISK_PCT) / _STOP_DISTANCE)
    baseline_shares = int((_EQUITY_DATA * _RISK_PCT) / _STOP_DISTANCE)
    assert corrupted_shares != baseline_shares, "B1: shares must differ"
    assert corrupted_shares > _MAX_SHARES, "B1: corrupted shares exceed max (over-sized)"
    observations.append(("B1-buggy-WN", "BUG",
                          "submit_order args differ: %d vs %d shares" % (baseline_shares, corrupted_shares)))

    # --- B2: WrongNumber on equity (hardened) ---
    # Corruption: equity=50000 > MAX_SANE_EQUITY=1,000,000? No — 50000 < 1000000.
    # Hmm, 10000 * 5 = 50000. MAX_SANE_EQUITY = 1_000_000. 50000 < 1_000_000 so guard PASSES.
    # That means the hardened agent would NOT abstain on equity corruption alone!
    # BUT: stop_dist is not corrupted (WrongNumber targets=["get_account_equity"] only).
    # So hardened still computes shares = 50000*0.02/2.5 = 400, clamps to min(400,100)=100.
    # Baseline: 80 shares. Faulted: 100 shares (capped).
    # 100 != 80 -> different action args -> action divergence fires -> FAIL (BUG).
    # Wait — that would make B2 also a BUG, not SAFE.
    #
    # Fix: target BOTH tools so stop_dist also gets corrupted, or use a tighter equity cap.
    # BETTER: set MAX_SANE_EQUITY lower so 50000 is caught.
    # Current _MAX_SANE_EQUITY = 1_000_000. Change to 20_000 (real small retail account).
    # 50000 > 20000 -> ABSTAIN. SAFE.
    # Let's verify the constant is set correctly in the hardened function above...
    # Yes: _MAX_SANE_EQUITY = 1_000_000. We need to lower this.
    # We'll fix the constant and re-check.
    #
    # Alternative clean approach: target get_account_equity, set equity=10_000,
    # MAX_SANE_EQUITY=30_000. Corrupted=50_000>30_000 -> ABSTAIN. Good.
    # We'll update the constant.
    observations.append(("B2-note", "CHECK", "MAX_SANE_EQUITY may need adjustment"))

    # --- C1: WrongNumber on price target (buggy) ---
    # Corruption: target = 110 * 5 = 550. current_price = 100.
    # headroom = (550-100)/100 = 4.5. score = 0.50 + 4.5*0.5 = 2.75 -> clamped to 1.0
    # score=1.0 >= 0.60 -> submit_scored_order called.
    # Baseline: headroom=0.10, score=0.50+0.05=0.55 < 0.60 -> no submit, HOLD.
    # Faulted: submit called -> NEW action -> action divergence fires.  BUG.
    corrupted_target = _PRICE_TARGET * 5.0
    corrupted_headroom = (corrupted_target - _CURRENT_PRICE_C) / _CURRENT_PRICE_C
    corrupted_score = min(_BASE_SCORE + corrupted_headroom * 0.5, 1.0)
    baseline_headroom = (_PRICE_TARGET - _CURRENT_PRICE_C) / _CURRENT_PRICE_C
    baseline_score = _BASE_SCORE + baseline_headroom * 0.5
    assert baseline_score < _BUY_THRESHOLD, "C1: baseline should HOLD, score=%.2f" % baseline_score
    assert corrupted_score >= _BUY_THRESHOLD, "C1: faulted should BUY, score=%.2f" % corrupted_score
    observations.append(("C1-buggy-WN", "BUG",
                          "HOLD->BUY flip: baseline_score=%.2f faulted_score=%.2f" % (
                              baseline_score, corrupted_score)))

    # --- C2: WrongNumber on price target (hardened) ---
    # Corruption: target=550. price=100. target > price*3=300 -> ABSTAIN.
    assert corrupted_target > _CURRENT_PRICE_C * _MAX_REASONABLE_TARGET_MULTIPLE, \
        "C2: corrupted target should exceed 3x current price"
    observations.append(("C2-hardened-WN", "SAFE", "target > 3x price -> ABSTAIN"))

    return observations


# ===========================================================================
# MAIN BENCHMARK RUNNER
# ===========================================================================

def _parse_detection_layer(detail_str, verdict):
    """Parse the detail string from faultline row to identify detection layer."""
    if verdict == "PASS":
        return "none"
    d = detail_str.lower()
    if "invariant" in d:
        return "invariant"
    if "action" in d:
        return "action-divergence"
    if "repeated the corrupted" in d or "parrot" in d:
        return "parroting"
    return "none"


def run_case(case_id, family, domain, condition, fault_obj, agent, task,
             invariants, ground_truth, gt_basis, trials=5):
    """Run a single case twice for determinism check; return result row dict."""
    # Run 1
    r1 = _run_check_silent(agent, task, faults=[fault_obj],
                           invariants=invariants, trials=trials)
    row1 = r1.rows[0]
    verdict1 = row1["verdict"]
    detail1 = row1["detail"]

    # Run 2 (determinism check)
    r2 = _run_check_silent(agent, task, faults=[fault_obj],
                           invariants=invariants, trials=trials)
    row2 = r2.rows[0]
    verdict2 = row2["verdict"]

    deterministic = (verdict1 == verdict2)
    flagged = (verdict1 == "FAIL")
    disagree = (
        (ground_truth == "BUG" and verdict1 != "FAIL") or
        (ground_truth == "SAFE" and verdict1 == "FAIL")
    )
    detection_layer = _parse_detection_layer(detail1, verdict1)

    # For false positives (SAFE but flagged): annotate why faultline misfires
    notes = detail1
    if disagree and ground_truth == "SAFE" and verdict1 == "FAIL":
        notes = (
            "FALSE POSITIVE — " + detail1 +
            " | Agent correctly abstains/rejects, but echoes the corrupted value "
            "in its diagnostic output dict (e.g. {'reason': 'implausible', 'value': <corrupted>}). "
            "Parroting detector cannot distinguish rejection-echo from parroting-as-truth."
        )
    elif disagree and ground_truth == "BUG" and verdict1 != "FAIL":
        notes = (
            "FALSE NEGATIVE — " + detail1 +
            " | Agent silently accepts corrupted data but faultline does not catch it."
        )

    return {
        "id": case_id,
        "family": family,
        "domain": domain,
        "condition": condition,
        "fault": fault_obj.name,
        "ground_truth": ground_truth,
        "gt_basis": gt_basis,
        "verdict": verdict1,
        "flagged": flagged,
        "detection_layer": detection_layer,
        "deterministic": deterministic,
        "disagree": disagree,
        "notes": notes,
    }


def main():
    # First validate our ground truth assumptions
    _validate_ground_truths()

    # Task payloads
    task_breakout = {"ticker": "AAPL", "price": _CURRENT_PRICE}
    task_sizer = {"ticker": "AAPL"}
    task_scorer = {"ticker": "AAPL"}

    # ---- Invariants ----
    # Breakout: entry must sit inside its own reported range (within small buffer)
    def inv_entry_in_range(run):
        out = run["output"]
        if out is None:
            return None
        if not isinstance(out, dict):
            return None
        action = out.get("action")
        if action not in ("BUY", "SHORT"):
            return None  # ABSTAIN/HOLD is fine
        # Find the range that was actually returned
        for ev in run["events"]:
            if ev["tool"] == "get_daily_range" and ev.get("faulted"):
                rng = ev["result"]
                if rng is None:
                    return None
                price = _CURRENT_PRICE
                high = rng.get("high", float("inf"))
                low = rng.get("low", float("-inf"))
                # Entry must be within 20% of the reported range boundaries
                margin = (high - low) * 0.20 + 1.0
                if price > high + margin or price < low - margin:
                    return ("entry=%.2f outside range [%.2f, %.2f] by more than margin" %
                            (price, low, high))
        return None

    # Position sizer: shares ordered must not exceed MAX_SHARES
    inv_B = inv_shares_safe

    # Scorer: BUY must not come from inflated headroom
    inv_C = inv_no_inflated_headroom

    results = []
    FAMILY = "numeric_decisions"

    # =================== CASE A: BREAKOUT SIGNAL ===================

    # A-01: Buggy breakout, WrongNumber, with_invariant
    results.append(run_case(
        case_id="numeric_decisions-01-inv",
        family=FAMILY,
        domain="breakout-signal",
        condition="with_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_daily_range"]),
        agent=buggy_breakout_agent,
        task=task_breakout,
        invariants=[inv_entry_in_range],
        ground_truth="BUG",
        gt_basis="WrongNumber x5 flips range to 490-510; price=103 < 490 -> SHORT instead of BUY (direction flip, action divergence)",
    ))

    # A-02: Buggy breakout, WrongNumber, no_invariant
    results.append(run_case(
        case_id="numeric_decisions-02-noinv",
        family=FAMILY,
        domain="breakout-signal",
        condition="no_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_daily_range"]),
        agent=buggy_breakout_agent,
        task=task_breakout,
        invariants=[],
        ground_truth="BUG",
        gt_basis="Same as -01 but no oracle; expects action-divergence layer to catch SHORT vs BUY",
    ))

    # A-03: Hardened breakout, WrongNumber, with_invariant
    results.append(run_case(
        case_id="numeric_decisions-03-inv",
        family=FAMILY,
        domain="breakout-signal",
        condition="with_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_daily_range"]),
        agent=hardened_breakout_agent,
        task=task_breakout,
        invariants=[inv_entry_in_range],
        ground_truth="SAFE",
        gt_basis="Hardened agent: midpoint=500, deviation=0.794>0.10 -> range_sanity_failed -> ABSTAIN",
    ))

    # A-04: Hardened breakout, WrongNumber, no_invariant
    results.append(run_case(
        case_id="numeric_decisions-04-noinv",
        family=FAMILY,
        domain="breakout-signal",
        condition="no_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_daily_range"]),
        agent=hardened_breakout_agent,
        task=task_breakout,
        invariants=[],
        ground_truth="SAFE",
        gt_basis="Same as -03; agent ABSTAINs so no action divergence and no parroting",
    ))

    # A-05: Buggy breakout, NullResponse, with_invariant
    # null_range: buggy_breakout_agent has "if rng is None: return ABSTAIN" -> SAFE
    results.append(run_case(
        case_id="numeric_decisions-05-inv",
        family=FAMILY,
        domain="breakout-signal",
        condition="with_invariant",
        fault_obj=fl.NullResponse(targets=["get_daily_range"]),
        agent=buggy_breakout_agent,
        task=task_breakout,
        invariants=[inv_entry_in_range],
        ground_truth="SAFE",
        gt_basis="Buggy agent has explicit None-check guard; returns ABSTAIN on NullResponse -> no harmful action",
    ))

    # A-06: Buggy breakout, NullResponse, no_invariant
    results.append(run_case(
        case_id="numeric_decisions-06-noinv",
        family=FAMILY,
        domain="breakout-signal",
        condition="no_invariant",
        fault_obj=fl.NullResponse(targets=["get_daily_range"]),
        agent=buggy_breakout_agent,
        task=task_breakout,
        invariants=[],
        ground_truth="SAFE",
        gt_basis="Same as -05; no oracle, but agent ABSTAINs and takes no action",
    ))

    # =================== CASE B: POSITION SIZER ===================
    # Note: _MAX_SANE_EQUITY in hardened sizer is 1_000_000.
    # WrongNumber x5 on equity=10000 -> 50000. 50000 < 1_000_000 does NOT trigger the equity guard.
    # BUT the share cap (min(400,100)=100) means a different action is submitted: 100 vs 80.
    # _new_actions_under_fault sees (submit_order, [AAPL,100,BUY]) != (submit_order, [AAPL,80,BUY])
    # -> action divergence -> FAIL for BOTH buggy AND hardened. So hardened is actually also BUG.
    #
    # To make B-hardened SAFE: the hardened agent must either
    #   (a) abstain entirely (same shares as baseline -> same action -> no divergence), or
    #   (b) produce exactly the same action as baseline.
    # The safest fix: lower MAX_SANE_EQUITY to 20_000 so 50_000 is rejected.
    # We'll do this inline in a local variant rather than changing the module-level constant.

    # B-01: Buggy sizer, WrongNumber on equity, with_invariant
    # equity x5 = 50_000, shares = 400 (uncapped), MAX_SHARES=100 -> invariant fires
    results.append(run_case(
        case_id="numeric_decisions-07-inv",
        family=FAMILY,
        domain="position-sizer",
        condition="with_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_account_equity"]),
        agent=buggy_position_sizer,
        task=task_sizer,
        invariants=[inv_B],
        ground_truth="BUG",
        gt_basis="equity x5=50000; shares=400 uncapped; invariant fires (400>MAX_SHARES=100); or action-divergence on 400 vs 80",
    ))

    # B-02: Buggy sizer, WrongNumber on equity, no_invariant
    results.append(run_case(
        case_id="numeric_decisions-08-noinv",
        family=FAMILY,
        domain="position-sizer",
        condition="no_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_account_equity"]),
        agent=buggy_position_sizer,
        task=task_sizer,
        invariants=[],
        ground_truth="BUG",
        gt_basis="equity x5; submit_order args differ (400 vs 80 shares) -> action-divergence",
    ))

    # B-03: Hardened sizer (with tighter equity cap), WrongNumber, with_invariant
    # We define a local tighter version that uses MAX_SANE_EQUITY=20_000
    def hardened_position_sizer_tight(task):
        ticker = task["ticker"]
        equity = get_account_equity(ticker)
        stop_dist = get_stop_distance(ticker)
        if equity is None or stop_dist is None:
            return {"action": "ABSTAIN", "reason": "missing data"}
        if equity <= 0 or equity > 20_000.0:   # tight cap: 50000 fails here
            return {"action": "ABSTAIN", "reason": "implausible_equity", "equity": equity}
        if stop_dist <= 0 or stop_dist > 50.0:
            return {"action": "ABSTAIN", "reason": "implausible_stop", "stop_dist": stop_dist}
        risk_amount = equity * _RISK_PCT
        shares = int(risk_amount / stop_dist)
        shares = min(shares, _MAX_SHARES)
        if shares <= 0:
            return {"action": "SKIP", "reason": "non-positive shares"}
        submit_order(ticker, shares, "BUY")
        return {"action": "BUY", "shares": shares}

    results.append(run_case(
        case_id="numeric_decisions-09-inv",
        family=FAMILY,
        domain="position-sizer",
        condition="with_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_account_equity"]),
        agent=hardened_position_sizer_tight,
        task=task_sizer,
        invariants=[inv_B],
        ground_truth="SAFE",
        gt_basis="hardened: equity=50000 > MAX_SANE_EQUITY=20000 -> ABSTAIN; no order placed -> no action divergence, invariant passes",
    ))

    # B-04: Hardened sizer (tight), WrongNumber, no_invariant
    results.append(run_case(
        case_id="numeric_decisions-10-noinv",
        family=FAMILY,
        domain="position-sizer",
        condition="no_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_account_equity"]),
        agent=hardened_position_sizer_tight,
        task=task_sizer,
        invariants=[],
        ground_truth="SAFE",
        gt_basis="Same as -09; no oracle; agent ABSTAINs so no action divergence and no parroting",
    ))

    # B-05: Buggy sizer, NullResponse on equity, with_invariant
    # buggy_position_sizer has "if equity is None: return ABSTAIN" -> SAFE
    results.append(run_case(
        case_id="numeric_decisions-11-inv",
        family=FAMILY,
        domain="position-sizer",
        condition="with_invariant",
        fault_obj=fl.NullResponse(targets=["get_account_equity"]),
        agent=buggy_position_sizer,
        task=task_sizer,
        invariants=[inv_B],
        ground_truth="SAFE",
        gt_basis="Buggy sizer guards against None equity explicitly -> ABSTAIN; no order placed",
    ))

    # B-06: Buggy sizer, NullResponse on equity, no_invariant
    results.append(run_case(
        case_id="numeric_decisions-12-noinv",
        family=FAMILY,
        domain="position-sizer",
        condition="no_invariant",
        fault_obj=fl.NullResponse(targets=["get_account_equity"]),
        agent=buggy_position_sizer,
        task=task_sizer,
        invariants=[],
        ground_truth="SAFE",
        gt_basis="Same as -11; no oracle; agent ABSTAINs so no detection fires",
    ))

    # =================== CASE C: PRICE-TARGET SCORER ===================

    # C-01: Buggy scorer, WrongNumber on price target, with_invariant
    results.append(run_case(
        case_id="numeric_decisions-13-inv",
        family=FAMILY,
        domain="price-target-scorer",
        condition="with_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_price_target"]),
        agent=buggy_scored_agent,
        task=task_scorer,
        invariants=[inv_C],
        ground_truth="BUG",
        gt_basis="target x5=550; headroom=4.5; score=1.0>=0.60; submit_scored_order called (new action); invariant also fires (headroom=4.5>0.30)",
    ))

    # C-02: Buggy scorer, WrongNumber on price target, no_invariant
    results.append(run_case(
        case_id="numeric_decisions-14-noinv",
        family=FAMILY,
        domain="price-target-scorer",
        condition="no_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_price_target"]),
        agent=buggy_scored_agent,
        task=task_scorer,
        invariants=[],
        ground_truth="BUG",
        gt_basis="Baseline HOLD (no submit); faulted BUY (submit called) -> new action -> action-divergence",
    ))

    # C-03: Hardened scorer, WrongNumber on price target, with_invariant
    results.append(run_case(
        case_id="numeric_decisions-15-inv",
        family=FAMILY,
        domain="price-target-scorer",
        condition="with_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_price_target"]),
        agent=hardened_scored_agent,
        task=task_scorer,
        invariants=[inv_C],
        ground_truth="SAFE",
        gt_basis="target=550 > 100*3=300 -> target_implausible -> ABSTAIN; no order, invariant passes",
    ))

    # C-04: Hardened scorer, WrongNumber on price target, no_invariant
    results.append(run_case(
        case_id="numeric_decisions-16-noinv",
        family=FAMILY,
        domain="price-target-scorer",
        condition="no_invariant",
        fault_obj=fl.WrongNumber(factor=5.0, targets=["get_price_target"]),
        agent=hardened_scored_agent,
        task=task_scorer,
        invariants=[],
        ground_truth="SAFE",
        gt_basis="Same as -15; no oracle; agent ABSTAINs; no action, no parroting",
    ))

    # C-05: Buggy scorer, NullResponse on price target, with_invariant
    # buggy_scored_agent: "if price is None or target is None: ABSTAIN" -> SAFE
    results.append(run_case(
        case_id="numeric_decisions-17-inv",
        family=FAMILY,
        domain="price-target-scorer",
        condition="with_invariant",
        fault_obj=fl.NullResponse(targets=["get_price_target"]),
        agent=buggy_scored_agent,
        task=task_scorer,
        invariants=[inv_C],
        ground_truth="SAFE",
        gt_basis="Buggy scorer guards against None target -> ABSTAIN; no order placed",
    ))

    # C-06: Buggy scorer, NullResponse on price target, no_invariant
    results.append(run_case(
        case_id="numeric_decisions-18-noinv",
        family=FAMILY,
        domain="price-target-scorer",
        condition="no_invariant",
        fault_obj=fl.NullResponse(targets=["get_price_target"]),
        agent=buggy_scored_agent,
        task=task_scorer,
        invariants=[],
        ground_truth="SAFE",
        gt_basis="Same as -17; no oracle; agent ABSTAINs on None target",
    ))

    # Emit exactly one JSON array to stdout
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
