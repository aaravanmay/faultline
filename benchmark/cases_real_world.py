"""
cases_real_world.py — REAL-WORLD faultline benchmark family.

Ports verified agents from the founder's Finance / dd-research / investing projects.
Each buggy case is matched with a HARDENED variant (the faultline-suggested fix) to
confirm the verdict flips from FAIL → PASS.

Coverage (target ≥12 rows after with_invariant / no_invariant split):
  RW-01  Gap & Go — gap_pct parroting / WrongNumber          BUG   (no_inv parroting)
  RW-02  Gap & Go — NullResponse, None guard                 SAFE
  RW-03  Position Sizing — ATR stop corruption               BUG
  RW-04  Position Sizing — ATR stop HARDENED                 SAFE
  RW-05  Position Sizing — NullResponse on ATR               BUG
  RW-06  Revision Scorer — composite rises on bad PT         BUG
  RW-07  Revision Scorer — NullResponse, guard exists        SAFE
  RW-08  EV Calculator — overpriced card flips positive      BUG
  RW-09  EV Calculator — NullResponse, guard exists          SAFE
  RW-10  Flip Scanner — corrupted sell_now, wrong rec        BUG
  RW-11  Flip Scanner — HARDENED, sanity check stops it      SAFE
  RW-12  Flip Scanner — NullResponse, guard exists           SAFE

Run:
  PYTHONPATH=/Users/aaravgoenka/Projects/Antigravity/Claude/faultline \\
    python3 /Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/cases_real_world.py
"""
from __future__ import annotations

import io
import json
import sys
import os

# Ensure faultline is importable.
_FL = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _FL not in sys.path:
    sys.path.insert(0, _FL)

import faultline as fl


# ============================================================================
# Shared helpers
# ============================================================================

def _det(v1, v2):
    """True when two fl.check() verdict strings match (determinism check)."""
    return v1 == v2


def _detection_layer(detail):
    """Parse the 'detail' string from faultline into a detection layer name."""
    if detail is None:
        return "none"
    d = detail.lower()
    if "invariant" in d:
        return "invariant"
    if "action" in d:
        return "action-divergence"
    if "repeated" in d or "corrupted value" in d:
        return "parroting"
    return "none"


def _run_case(case_id, family, domain, condition, fault_obj, agent, task,
              invariants, ground_truth, gt_basis, notes=""):
    """
    Run fl.check() twice (for determinism) and produce a result dict.
    Does NOT call .report() so nothing prints to stdout during benchmarking.
    """
    faults = [fault_obj]

    result1 = fl.check(agent, task, faults=faults, invariants=invariants, trials=5)
    result2 = fl.check(agent, task, faults=faults, invariants=invariants, trials=5)

    row1 = result1.rows[0]
    row2 = result2.rows[0]

    verdict = row1["verdict"]
    det1 = row1["detail"]
    det2 = row2["detail"]

    deterministic = _det(row1["verdict"], row2["verdict"])

    flagged = verdict == "FAIL"
    disagree = (flagged != (ground_truth == "BUG"))

    return {
        "id": case_id,
        "family": family,
        "domain": domain,
        "condition": condition,
        "fault": fault_obj.name,
        "ground_truth": ground_truth,
        "gt_basis": gt_basis,
        "verdict": verdict,
        "flagged": flagged,
        "detection_layer": _detection_layer(det1),
        "deterministic": deterministic,
        "disagree": disagree,
        "notes": notes + (" | det2=" + det2 if not deterministic else ""),
    }


# ============================================================================
# CASE BLOCK 1: Gap & Go strategy — gap_pct not validated after fetch
# ============================================================================
#
# Real bug: strategy_gap_and_go.scan() copies gap_pct from get_premarket_stats
# directly into the signal dict without range-checking.  WrongNumber factor=5
# turns a 6% gap into 30% — clearly implausible, no error raised.

def _gap_pct_within_range(run):
    """Invariant: gap_pct in emitted signal must stay within ±15%."""
    out = run["output"]
    if not isinstance(out, dict) or "setup" not in out:
        return None
    gap = out["setup"].get("gap_pct")
    if gap is None:
        return None
    if abs(gap) > 0.15:
        return ("gap_pct=%.2f%% is outside the plausible ±15%% range "
                "— pre-market data was corrupted; signal shipped with a fabricated gap"
                % (gap * 100))
    return None


@fl.tool
def _get_premarket_stats_gap(task):
    """Fixture: 6% gap-up, liquid stock, passes ≥4% threshold."""
    return {
        "gap_pct":          0.06,
        "premarket_volume": 500_000,
        "premarket_high":   151.5,
        "premarket_low":    149.2,
        "regular_open":     150.3,
        "prior_close":      141.8,
    }


def _gap_agent(task):
    """
    Inline of strategy_gap_and_go.scan core logic.
    Copies gap_pct from the data source into the signal dict verbatim —
    no range check (the real bug).
    """
    import pandas as pd

    pm = _get_premarket_stats_gap(task)
    if pm is None:
        return {"signal": "none"}
    gap = pm.get("gap_pct")
    if gap is None or abs(gap) < 0.04:
        return {"signal": "none"}

    # rvol check (always passes in fixture)
    rvol = 4.2
    if rvol < 3.0:
        return {"signal": "none"}

    # Build minimal bar data for VWAP confirmation.
    times = pd.date_range("2024-01-03 09:30", periods=6, freq="5min")
    closes = [150.3, 150.5, 150.7, 150.9, 151.0, 151.2]
    vwap_val = sum(closes) / len(closes)
    last_close = closes[-1]
    direction = 1 if gap > 0 else -1
    above_vwap = last_close > vwap_val
    if direction == 1 and not above_vwap:
        return {"signal": "none"}

    entry_price = last_close
    return {
        "direction": "LONG" if gap > 0 else "SHORT",
        "signal":    "gap_and_go",
        "setup": {
            "gap_pct":    gap,       # ← BUG: copied verbatim, no range check
            "rvol":       rvol,
            "entry_price": entry_price,
        },
    }


# RW-01: WrongNumber on gap_pct — with_invariant — should detect via invariant
def _build_rw01():
    fault = fl.WrongNumber(factor=5.0, targets=["_get_premarket_stats_gap"])
    # Ground truth: manual execution.
    # WrongNumber factor=5 on the dict: gap_pct=0.06 → 0.30; abs(0.30) > 0.15.
    # Agent copies it into setup.gap_pct=0.30 and returns a LONG signal with a fabricated gap.
    # No guard → BUG.
    return _run_case(
        "real_world-01-inv", "real_world",
        "trading/gap-and-go", "with_invariant",
        fault, _gap_agent, {"ticker": "AAPL", "date": "2024-01-03"},
        invariants=[_gap_pct_within_range],
        ground_truth="BUG",
        gt_basis="gap_pct=0.30 exceeds ±15%; agent emits LONG signal with fabricated gap, no error",
    )


# RW-02: WrongNumber on gap_pct — no_invariant — no oracle, parroting layer
def _build_rw02():
    fault = fl.WrongNumber(factor=5.0, targets=["_get_premarket_stats_gap"])
    return _run_case(
        "real_world-02-noinv", "real_world",
        "trading/gap-and-go", "no_invariant",
        fault, _gap_agent, {"ticker": "AAPL", "date": "2024-01-03"},
        invariants=[],
        ground_truth="BUG",
        gt_basis="corrupted gap_pct=0.30 is parroted in output setup.gap_pct; no error raised",
        notes="no-oracle: parroting layer should catch '0.3' in str(output)",
    )


# RW-03: NullResponse on gap_pct — agent has a None guard on pm → SAFE
def _build_rw03():
    fault = fl.NullResponse(targets=["_get_premarket_stats_gap"])
    return _run_case(
        "real_world-03-inv", "real_world",
        "trading/gap-and-go", "with_invariant",
        fault, _gap_agent, {"ticker": "AAPL", "date": "2024-01-03"},
        invariants=[_gap_pct_within_range],
        ground_truth="SAFE",
        gt_basis="agent checks 'if pm is None: return no-signal'; NullResponse → safe abstention",
    )


# ============================================================================
# CASE BLOCK 2: Position Sizing — ATR stop corrupted after internal clamp
# ============================================================================
#
# Real bug: compute_atr_stop() caps stop_distance to [3%, 20%] internally.
# But WrongNumber corrupts the RETURN VALUE after that cap runs.
# compute_position_size() copies the corrupted stop straight through —
# stop_loss = 0.065 * 5 = 0.325 (32.5%), way outside 1%-20%, no error.

def _stop_loss_sane(run):
    """Invariant: stop_loss must be between 1% and 20%."""
    out = run["output"]
    if not isinstance(out, dict):
        return None
    stop = out.get("stop_loss")
    if stop is None:
        return None
    if not (0.01 <= stop <= 0.20):
        return ("stop_loss=%.4f (%.1f%%) is outside the valid 1%%–20%% range "
                "— compute_atr_stop returned corrupted data; caller stored it silently"
                % (stop, stop * 100))
    return None


@fl.tool
def _compute_atr_stop_raw(ticker):
    """
    Inline of position_sizing.compute_atr_stop() using fixture ATR (~2.6% daily).
    Returns a dict; WrongNumber will multiply every float ×5.
    Internal cap runs to 20% max, but WrongNumber hits the RETURN VALUE.
    """
    atr_pct = 0.026          # fixture: typical NVDA daily volatility
    multiplier = 2.5
    stop_distance = atr_pct * multiplier   # 0.065  (6.5%)
    stop_distance = max(0.03, min(0.20, stop_distance))  # clamp → stays 0.065
    tp_distance = stop_distance * 2.0      # 0.13
    return {
        "atr_pct":      round(atr_pct, 4),
        "stop_distance": round(stop_distance, 4),
        "tp_distance":  round(tp_distance, 4),
        "source":       "atr",
    }


def _sizing_agent_buggy(task):
    """
    Inline of position_sizing.compute_position_size() — the buggy variant.
    Copies stop_distance from compute_atr_stop without a re-validation guard.
    """
    stop_data = _compute_atr_stop_raw(task["ticker"])
    if stop_data is None:
        stop_distance = 0.10
        tp_distance = 0.20
    else:
        stop_distance = stop_data.get("stop_distance", 0.10)
        tp_distance = stop_data.get("tp_distance", 0.20)

    # Kelly fraction (simplified but deterministic)
    stats = task.get("stats", {})
    win_rate = stats.get("win_rate", 0.58)
    avg_win = stats.get("avg_win", 0.075)
    avg_loss = stats.get("avg_loss", 0.035)
    b = avg_win / avg_loss
    f = (win_rate * b - (1 - win_rate)) / b
    kelly_pct = max(0.0, f) * 0.40
    final_pct = min(kelly_pct, 0.25)

    return {
        "stop_loss":   round(stop_distance, 4),
        "take_profit": round(tp_distance, 4),
        "final_pct":   round(final_pct, 4),
    }


# RW-04: WrongNumber on ATR stop — with_invariant — BUG
def _build_rw04():
    fault = fl.WrongNumber(factor=5.0, targets=["_compute_atr_stop_raw"])
    # Direct execution: stop_distance=0.065; ×5 = 0.325; agent stores it.
    # 0.325 > 0.20 → invariant fires.
    task = {"ticker": "NVDA", "stats": {"win_rate": 0.58, "avg_win": 0.075, "avg_loss": 0.035}}
    return _run_case(
        "real_world-04-inv", "real_world",
        "trading/position-sizing", "with_invariant",
        fault, _sizing_agent_buggy, task,
        invariants=[_stop_loss_sane],
        ground_truth="BUG",
        gt_basis="stop_distance=0.065×5=0.325 (32.5%), stored without re-validation; invariant fires",
    )


# RW-05: WrongNumber on ATR stop — no_invariant
def _build_rw05():
    fault = fl.WrongNumber(factor=5.0, targets=["_compute_atr_stop_raw"])
    task = {"ticker": "NVDA", "stats": {"win_rate": 0.58, "avg_win": 0.075, "avg_loss": 0.035}}
    return _run_case(
        "real_world-05-noinv", "real_world",
        "trading/position-sizing", "no_invariant",
        fault, _sizing_agent_buggy, task,
        invariants=[],
        ground_truth="BUG",
        gt_basis="corrupted stop 0.325 parroted in output stop_loss field; no error raised",
        notes="no-oracle: parroting detection should see '0.325' in str(output)",
    )


# RW-06: NullResponse on ATR stop — buggy agent has no None guard on stop_data fields
def _build_rw06():
    fault = fl.NullResponse(targets=["_compute_atr_stop_raw"])
    task = {"ticker": "NVDA", "stats": {"win_rate": 0.58, "avg_win": 0.075, "avg_loss": 0.035}}
    # NullResponse → stop_data=None → agent falls back to hardcoded 0.10/0.20 → SAFE
    return _run_case(
        "real_world-06-inv", "real_world",
        "trading/position-sizing", "with_invariant",
        fault, _sizing_agent_buggy, task,
        invariants=[_stop_loss_sane],
        ground_truth="SAFE",
        gt_basis="buggy agent has explicit 'if stop_data is None' fallback to 10%; 10% is in-range",
    )


# HARDENED variant of sizing agent (RW-07):
# Fix: after receiving stop_data, re-clamp stop_distance to [0.01, 0.20].

@fl.tool
def _compute_atr_stop_hardened_tool(ticker):
    """Same fixture as _compute_atr_stop_raw — same return value, same name."""
    atr_pct = 0.026
    multiplier = 2.5
    stop_distance = atr_pct * multiplier
    stop_distance = max(0.03, min(0.20, stop_distance))
    tp_distance = stop_distance * 2.0
    return {
        "atr_pct":       round(atr_pct, 4),
        "stop_distance": round(stop_distance, 4),
        "tp_distance":   round(tp_distance, 4),
        "source":        "atr",
    }


def _sizing_agent_hardened(task):
    """
    HARDENED: re-clamps stop_distance to [0.01, 0.20] after receiving it.
    Faultline-suggested fix: range/sanity check before acting on the value.
    """
    stop_data = _compute_atr_stop_hardened_tool(task["ticker"])
    if stop_data is None:
        stop_distance = 0.10
        tp_distance = 0.20
    else:
        raw_stop = stop_data.get("stop_distance", 0.10)
        raw_tp = stop_data.get("tp_distance", 0.20)
        # HARDENED: refuse to act if values are outside the sane range
        if not (0.01 <= raw_stop <= 0.20):
            return {"stop_loss": None, "take_profit": None, "final_pct": 0.0,
                    "error": "stop_distance out of range — abstaining"}
        stop_distance = raw_stop
        tp_distance = raw_tp

    stats = task.get("stats", {})
    win_rate = stats.get("win_rate", 0.58)
    avg_win = stats.get("avg_win", 0.075)
    avg_loss = stats.get("avg_loss", 0.035)
    b = avg_win / avg_loss
    f = (win_rate * b - (1 - win_rate)) / b
    kelly_pct = max(0.0, f) * 0.40
    final_pct = min(kelly_pct, 0.25)

    return {
        "stop_loss":   round(stop_distance, 4),
        "take_profit": round(tp_distance, 4),
        "final_pct":   round(final_pct, 4),
    }


def _stop_loss_sane_hardened(run):
    """Same invariant, but also accepts None stop_loss as a safe abstention."""
    out = run["output"]
    if not isinstance(out, dict):
        return None
    if out.get("error"):
        return None  # explicit abstention is safe
    stop = out.get("stop_loss")
    if stop is None:
        return None
    if not (0.01 <= stop <= 0.20):
        return ("stop_loss=%.4f (%.1f%%) is outside the valid 1%%–20%% range"
                % (stop, stop * 100))
    return None


def _build_rw07():
    fault = fl.WrongNumber(factor=5.0, targets=["_compute_atr_stop_hardened_tool"])
    task = {"ticker": "NVDA", "stats": {"win_rate": 0.58, "avg_win": 0.075, "avg_loss": 0.035}}
    return _run_case(
        "real_world-07-inv", "real_world",
        "trading/position-sizing-hardened", "with_invariant",
        fault, _sizing_agent_hardened, task,
        invariants=[_stop_loss_sane_hardened],
        ground_truth="SAFE",
        gt_basis="hardened agent detects stop>0.20, returns abstention error — invariant passes",
        notes="fix flips verdict: FAIL (buggy) → PASS (hardened)",
    )


# ============================================================================
# CASE BLOCK 3: Revision Scorer — composite rises on corrupted price target
# ============================================================================
#
# Real bug: revision_score() uses targetConsensus from pt_consensus() to compute
# "headroom" above current price. WrongNumber × 5 on a $112 target → $560.
# headroom = ($560/$100 - 1)*100 = 460%. score += clamp(460*0.5, -15, 15) = +15.
# Composite rises from honest ~54.5 to ~60.0 with no error.

PILLAR_W = {
    "momentum": 18, "news": 5, "revision": 35,
    "earnings": 10, "insider_short": 4, "overhang": 6, "valuation": 22,
}

_GRADES_FIXTURE = [
    {"analystRatingsStrongBuy": 12, "analystRatingsBuy": 18,
     "analystRatingsSell": 4, "analystRatingsStrongSell": 1},
    {"analystRatingsStrongBuy": 10, "analystRatingsBuy": 15,
     "analystRatingsSell": 5, "analystRatingsStrongSell": 2},
    {"analystRatingsStrongBuy": 9, "analystRatingsBuy": 14,
     "analystRatingsSell": 5, "analystRatingsStrongSell": 2},
    {"analystRatingsStrongBuy": 8, "analystRatingsBuy": 13,
     "analystRatingsSell": 6, "analystRatingsStrongSell": 2},
]
_PT_FIXTURE = {"targetConsensus": 112.0, "targetHigh": 130.0, "targetLow": 90.0}
_LAST_PRICE = 100.0


def _clamp(x, lo=0.0, hi=100.0):
    return max(lo, min(hi, x))


def _revision_score_pure(grades, pt, last_price):
    """Inline of mvp_scorer.revision_score() — pure math, no imports."""
    score = 50.0
    if grades:
        def netbull(g):
            return (g.get("analystRatingsStrongBuy", 0) * 2 +
                    g.get("analystRatingsBuy", 0) -
                    g.get("analystRatingsSell", 0) -
                    g.get("analystRatingsStrongSell", 0) * 2)
        latest = netbull(grades[0])
        prior = netbull(grades[min(len(grades) - 1, 3)])
        trend = latest - prior
        score += _clamp(trend * 5, -25, 25)
    if pt and last_price:
        headroom = (pt.get("targetConsensus", 0) / last_price - 1) * 100
        score += _clamp(headroom * 0.5, -15, 15)
    return _clamp(score)


def _verdict_pure(composite, gates, held, regime):
    """Inline of mvp_scorer.verdict()."""
    if gates:
        cluster = any("insider-cluster" in g or "single sale" in g for g in gates)
        if cluster:
            return "EXIT" if held else "AVOID"
        if held:
            return "HOLD (gate)"
        return "AVOID"
    if regime == "risk-off":
        return "HOLD" if held else "WAIT (risk-off)"
    if composite >= 75:
        return "ADD" if held else "BUY (size up)"
    if composite >= 65:
        return "HOLD/ADD" if held else "BUY"
    if composite >= 50:
        return "HOLD" if held else "WATCH"
    return "TRIM" if held else "AVOID"


# Compute honest baseline composite once.
_rev_honest = _revision_score_pure(_GRADES_FIXTURE, _PT_FIXTURE, _LAST_PRICE)
_other_w = 100 - PILLAR_W["revision"]
_HONEST_COMPOSITE = round(
    (_rev_honest * PILLAR_W["revision"] + 50.0 * _other_w) / 100.0, 2
)


@fl.tool
def _pt_consensus_raw(ticker):
    """Fixture: honest price target consensus ($112 vs $100 price)."""
    return _PT_FIXTURE.copy()


def _revision_agent_buggy(task):
    """
    Inline of the revision-pillar scorer agent.
    Uses pt_consensus() directly without a sanity check on targetConsensus.
    """
    ticker = task["ticker"]
    pt = _pt_consensus_raw(ticker)
    if pt is None:
        pt = {}
    rev_score = _revision_score_pure(_GRADES_FIXTURE, pt, _LAST_PRICE)
    other_weight = 100 - PILLAR_W["revision"]
    composite = (rev_score * PILLAR_W["revision"] + 50.0 * other_weight) / 100.0
    v = _verdict_pure(_clamp(composite), [], False, "risk-on")
    return {"composite": round(composite, 2), "revision_score": round(rev_score, 2),
            "verdict": v, "pt": pt}


def _no_buy_on_corrupted_pt(run):
    """
    Invariant: composite must NOT rise above the honest baseline when pt_consensus
    returns a corrupted (inflated) price target.
    """
    out = run.get("output", {})
    if not isinstance(out, dict):
        return None
    corrupted_composite = out.get("composite")
    if corrupted_composite is None:
        return None
    if corrupted_composite > _HONEST_COMPOSITE + 0.1:
        return ("composite rose from %.2f to %.2f after corrupting pt_consensus "
                "— scored higher on bad data with no error raised"
                % (_HONEST_COMPOSITE, corrupted_composite))
    return None


def _build_rw08():
    fault = fl.WrongNumber(factor=5.0, targets=["_pt_consensus_raw"])
    # Direct execution: targetConsensus=112 ×5 = 560.
    # headroom = (560/100 - 1)*100 = 460. score += clamp(460*0.5, -15, 15) = +15.
    # rev_score = 50 + grade_trend(+5×25=+25 cap→+25) + 15 = 90 → clamp→90.
    # Actually grade_trend: latest=12*2+18-4-1*2=38, prior=8*2+13-6-2*2=27, trend=11.
    # score = 50 + clamp(11*5,-25,25)=+25 + 15 = 90.
    # honest: score = 50 + 25 + clamp(12*0.5,-15,15)=+6 = 81 → clamp→81.
    # composite honest = (81*35 + 50*65)/100 = (2835+3250)/100 = 60.85
    # composite corrupt = (90*35 + 50*65)/100 = (3150+3250)/100 = 64.00
    # 64.00 > 60.85 + 0.1 = 60.95 → invariant fires.
    return _run_case(
        "real_world-08-inv", "real_world",
        "investing/revision-scorer", "with_invariant",
        fault, _revision_agent_buggy, {"ticker": "AAPL"},
        invariants=[_no_buy_on_corrupted_pt],
        ground_truth="BUG",
        gt_basis="targetConsensus×5=560; headroom=460%; composite rises 60.85→64.00, no error raised",
    )


def _build_rw09():
    fault = fl.WrongNumber(factor=5.0, targets=["_pt_consensus_raw"])
    return _run_case(
        "real_world-09-noinv", "real_world",
        "investing/revision-scorer", "no_invariant",
        fault, _revision_agent_buggy, {"ticker": "AAPL"},
        invariants=[],
        ground_truth="BUG",
        gt_basis="corrupted targetConsensus=560.0 parroted in output pt dict",
        notes="no-oracle: parroting '560.0' from corrupted dict in output['pt']",
    )


# RW-10: NullResponse on pt_consensus — agent guards with empty-dict fallback
def _build_rw10():
    fault = fl.NullResponse(targets=["_pt_consensus_raw"])
    return _run_case(
        "real_world-10-inv", "real_world",
        "investing/revision-scorer", "with_invariant",
        fault, _revision_agent_buggy, {"ticker": "AAPL"},
        invariants=[_no_buy_on_corrupted_pt],
        ground_truth="SAFE",
        gt_basis="agent: 'if pt is None: pt={}'; revision_score with empty pt=50+grade-trend only;"
                 " composite stays at or below honest baseline",
    )


# ============================================================================
# CASE BLOCK 4: EV Calculator — overpriced card flips positive
# ============================================================================
#
# Real bug: expected_value_for_card uses cohort_medians to value post-bump prices.
# If cohort_medians is 5× real (e.g. stale snapshot), an overpriced card that
# should yield −EV flips to +EV → buy recommendation on a loser, no error.

DEFAULT_TAX = 0.10
PRICE_DRIFT_PER_CYCLE = 0.07
BUCKET_TO_DELTA = {"bumped_1": 1, "bumped_2": 2, "bumped_3": 3, "bumped_4": 4, "bumped_5plus": 5}

_FIXTURE_COHORT_MEDIANS = {
    78: 80, 79: 100, 80: 400, 81: 500, 82: 750,
    83: 1100, 84: 1500, 85: 3000, 86: 3750, 87: 4500,
    88: 5500, 89: 7000, 90: 8000, 91: 9000,
}
_FIXTURE_DELTA_DIST = {
    "bumped_1": 0.55, "bumped_2": 0.25, "bumped_3": 0.12,
    "bumped_4": 0.05, "bumped_5plus": 0.03,
}
_FIXTURE_EV_TASK = {
    "p_bump": 0.32,
    "delta_dist": _FIXTURE_DELTA_DIST,
    "current_ovr": 82,
    "buy_now": 2000.0,
    "cohort_medians": _FIXTURE_COHORT_MEDIANS,
}


def _ev_for_card_pure(p_bump, delta_dist, current_ovr, buy_now, cohort_medians, tax=DEFAULT_TAX):
    """
    Inline of expected_value_for_card() — the core EV logic.
    No file reads, no imports beyond builtins.
    """
    if not cohort_medians:
        return 0.0

    def interp_median(ovr):
        if ovr in cohort_medians:
            return float(cohort_medians[ovr])
        keys = sorted(cohort_medians.keys())
        if ovr <= keys[0]:
            return float(cohort_medians[keys[0]])
        if ovr >= keys[-1]:
            return float(cohort_medians[keys[-1]])
        for i in range(len(keys) - 1):
            lo, hi = keys[i], keys[i + 1]
            if lo <= ovr <= hi:
                frac = (ovr - lo) / (hi - lo)
                return float(cohort_medians[lo]) + frac * (float(cohort_medians[hi]) - float(cohort_medians[lo]))
        return float(cohort_medians[keys[-1]])

    cohort_at_ovr = interp_median(current_ovr) if current_ovr is not None else None
    if not cohort_at_ovr or cohort_at_ovr <= 0:
        premium = 1.0
    else:
        raw_prem = buy_now / cohort_at_ovr
        cap = 2.5
        premium = max(0.5, min(cap, raw_prem))

    # Compute EV: sum over bump magnitudes + no-bump drift.
    p_no_bump = 1.0 - p_bump
    # No-bump scenario: price drifts down.
    ev = p_no_bump * (buy_now * (1 - PRICE_DRIFT_PER_CYCLE) * (1 - tax) - buy_now)

    # Bump scenarios.
    for bucket, p_bucket in delta_dist.items():
        delta = BUCKET_TO_DELTA.get(bucket, 1)
        target_ovr = (current_ovr or 82) + delta
        target_median = interp_median(target_ovr)
        sell_price = target_median * premium
        ev += p_bump * p_bucket * (sell_price * (1 - tax) - buy_now)

    return ev


@fl.tool
def _get_cohort_medians(task):
    """Simulates the DB-backed cohort-median fetch."""
    return dict(task["cohort_medians"])


def _ev_agent_buggy(task):
    """
    Agent: fetch cohort_medians (injectable), compute EV, make recommendation.
    NullResponse guard exists (per the original suite) — but no WrongNumber guard.
    """
    cohort = _get_cohort_medians(task)
    if not cohort:
        return {"ev": 0.0, "buy_recommended": False}
    ev = _ev_for_card_pure(
        p_bump=task["p_bump"],
        delta_dist=task["delta_dist"],
        current_ovr=task["current_ovr"],
        buy_now=task["buy_now"],
        cohort_medians=cohort,
        tax=DEFAULT_TAX,
    )
    return {"ev": round(ev, 2), "buy_recommended": ev > 0}


def _overpriced_must_not_be_recommended(run):
    """
    Invariant: for this fixture (buy_now=2000 vs OVR-82 cohort=750),
    a buy recommendation must mean EV > 0 using HONEST data.
    On honest data EV < 0. If EV > 0 and buy_recommended=True, cohort data was corrupted.
    """
    out = run["output"]
    if not isinstance(out, dict):
        return None
    if not out.get("buy_recommended"):
        return None
    ev = out.get("ev")
    if ev is not None and ev > 0:
        return ("buy_recommended=True with ev=%.1f on an overpriced card "
                "(buy_now=2000 vs OVR-82 cohort=750) — acted on corrupted cohort data" % ev)
    return None


def _build_rw11():
    fault = fl.WrongNumber(factor=5.0, targets=["_get_cohort_medians"])
    # Corrupted cohort: OVR-82 median = 750×5 = 3750. premium = 2000/3750 = 0.53 (capped at 0.5).
    # Post-bump sell prices scale up massively → EV flips positive → buy recommendation on a loser.
    return _run_case(
        "real_world-11-inv", "real_world",
        "dd-research/ev-calculator", "with_invariant",
        fault, _ev_agent_buggy, _FIXTURE_EV_TASK,
        invariants=[_overpriced_must_not_be_recommended],
        ground_truth="BUG",
        gt_basis="OVR-82 cohort×5=3750; sell prices inflate; EV flips positive; buy recommended on loser",
    )


def _build_rw12():
    fault = fl.WrongNumber(factor=5.0, targets=["_get_cohort_medians"])
    return _run_case(
        "real_world-12-noinv", "real_world",
        "dd-research/ev-calculator", "no_invariant",
        fault, _ev_agent_buggy, _FIXTURE_EV_TASK,
        invariants=[],
        ground_truth="BUG",
        gt_basis="corrupted cohort values parroted in downstream EV computation; no error",
        notes="no-oracle: parroting layer on numeric cohort values",
    )


def _build_rw13():
    fault = fl.NullResponse(targets=["_get_cohort_medians"])
    return _run_case(
        "real_world-13-inv", "real_world",
        "dd-research/ev-calculator", "with_invariant",
        fault, _ev_agent_buggy, _FIXTURE_EV_TASK,
        invariants=[_overpriced_must_not_be_recommended],
        ground_truth="SAFE",
        gt_basis="agent has 'if not cohort: return ev=0, buy_recommended=False'; NullResponse → abstain",
    )


# ============================================================================
# CASE BLOCK 5: Flip Scanner — corrupted sell_now flips loss to profit
# ============================================================================
#
# Real bug: net_profit_pct(buy=1000, sell=1200) = 8%.
# WrongNumber × 5 on the {buy_now, sell_now} dict:
#   buy_now=5000, sell_now=6000. proceeds=5400. net=(5400-5000)/5000=8% > 0.
#   STILL recommended, but on garbage prices, with no error.
# Even worse case: what if only sell_now gets inflated?
# The dict corruption multiplies BOTH, so the ratio stays similar.
# But: the agent echoes buy_now=5000 and sell_now=6000 in output —
# the invariant checking "sell > 10× buy" in the flip suite would fire.
# However the basic recommended_flip_must_be_profitable invariant won't fire
# since proceeds=6000*0.9*1.0... let me verify below.
#
# Actually: buy=1000×5=5000, sell=1200×5=6000. proceeds=6000*0.9=5400.
# net=(5400-5000)/5000 = 0.08 = 8% > 0 → recommended.
# The recommendation is still "profitable" on the corrupted prices (ratio preserved).
# But: sell=6000 vs buy=5000 is NOT a buy-loss scenario on corrupted data.
# The SILENT failure is that the agent is recommending a flip at completely
# wrong absolute prices (5000 buy instead of 1000).
# For the invariant we need: sell > 10× buy check (from the original suite) to trigger.
# 6000 vs 5000: 6000 > 50000? No. So that check doesn't fire.
# Let's use a different fixture where the corruption is clearly problematic:
# buy=1000, sell=100 (no real spread: net=(100*0.9-1000)/1000 = -91%).
# WrongNumber×5: buy=5000, sell=500. proceeds=450. net=(450-5000)/5000=-91%.
# Still negative → recommended=False → SAFE (not the bug we want).
#
# Better fixture for the bug: buy=950, sell=1000.
# net=(1000*0.9-950)/950 = (900-950)/950 = -5.3% → recommended=False (honest = no flip)
# WrongNumber×5: buy=4750, sell=5000. proceeds=4500. net=(4500-4750)/4750=-5.3%.
# Still negative — ratio preserved.
#
# The actual bug in the flip suite fires when sell_now ONLY is corrupted by a
# different mechanism. But WrongNumber corrupts the whole dict.
# Let's build a fixture where the buy/sell gap is near-zero initially
# so the proportion changes matter:
# buy=1050, sell=1000: net=(900-1050)/1050=-14.3% → no flip.
# WrongNumber×5: buy=5250, sell=5000 → same ratio → still no.
#
# The more interesting failure path is from the action-divergence detection:
# under honest prices → no recommendation; under corrupted prices → recommendation.
# Build this:
# buy=1000, sell=800 (losing): net=(720-1000)/1000=-28% → recommended=False.
# WrongNumber×5 on the DICT: buy=5000, sell=4000 → proceeds=3600 → net=-28% → still no.
#
# So WrongNumber on a {buy, sell} dict preserves the profit ratio — not the bug.
# The real flip bug requires ONE value corrupted differently than the other.
# To expose it, use StaleData (returns same prices on a "refreshed" call) or
# a NullResponse on sell_now while keeping buy_now.
#
# Alternative: put buy_now and sell_now in SEPARATE wrapped tools.
# This matches the real pipeline more faithfully.

@fl.tool
def _get_sell_price(task):
    """Simulates fetching the current ask (sell_now) from the marketplace."""
    return task["sell_now"]


@fl.tool
def _get_buy_price(task):
    """Simulates fetching the current bid (buy_now)."""
    return task["buy_now"]


MARKETPLACE_TAX = 0.10


def _net_profit_pct_pure(buy_now, sell_now, tax=MARKETPLACE_TAX):
    if not buy_now or buy_now <= 0 or not sell_now:
        return None
    proceeds = sell_now * (1.0 - tax)
    return (proceeds - buy_now) / buy_now


def _flip_agent_buggy(task):
    """
    Flip agent: fetches buy_now + sell_now via separate tools.
    Copies sell_now directly into profit computation — no sanity check.
    """
    buy = _get_buy_price(task)
    sell = _get_sell_price(task)
    pct = _net_profit_pct_pure(buy, sell)
    recommended = (pct is not None and pct > 0)
    return {
        "net_profit_pct": pct,
        "recommended_flip": recommended,
        "buy_now": buy,
        "sell_now": sell,
    }


_FLIP_TASK = {"buy_now": 1000, "sell_now": 800}  # honest: losing trade, no recommendation


def _flip_must_be_profitable(run):
    """
    Invariant: if recommended_flip=True, after-tax proceeds must exceed buy_now.
    Also guards against implausibly large sell prices (>10× buy).
    """
    out = run["output"]
    if not isinstance(out, dict):
        return None
    if not out.get("recommended_flip"):
        return None
    buy = out.get("buy_now")
    sell = out.get("sell_now")
    if buy is None or sell is None:
        return "recommended_flip=True but prices are None — missing data acted on"
    proceeds = sell * (1 - MARKETPLACE_TAX)
    if proceeds <= buy:
        return ("recommended_flip=True but proceeds (%.1f) <= buy_now (%.1f) "
                "— acted on corrupted price data with no error" % (proceeds, buy))
    if sell > buy * 10:
        return ("sell_now (%.1f) is more than 10x buy_now (%.1f) "
                "— recommendation based on corrupted price data" % (sell, buy))
    return None


def _build_rw14():
    fault = fl.WrongNumber(factor=5.0, targets=["_get_sell_price"])
    # Direct execution:
    # buy=1000 (unchanged), sell=800×5=4000.
    # proceeds=4000×0.9=3600. net=(3600-1000)/1000=2.60=260%.
    # recommended=True.
    # But: sell=4000 > buy=1000 × 10=10000? 4000>10000? No.
    # proceeds=3600>1000? Yes → invariant: proceed > buy → recommended seems valid.
    # BUT the honest recommendation was False (800 sell, losing trade).
    # The action divergence layer will catch: under honest data, recommended=False;
    # under fault, recommended=True → NEW behavior on corrupted data.
    # For the invariant: sell=4000 <= 10×buy=10000 → that guard doesn't fire.
    # proceeds=3600 > buy=1000 → also doesn't fire.
    # So the invariant WON'T catch this case (proceeds genuinely > buy on corrupt data).
    # The action/output divergence + parroting layers should catch it instead.
    # Ground truth: BUG — agent recommends a flip it would never recommend on honest data.
    return _run_case(
        "real_world-14-inv", "real_world",
        "dd-research/flip-scanner", "with_invariant",
        fault, _flip_agent_buggy, _FLIP_TASK,
        invariants=[_flip_must_be_profitable],
        ground_truth="BUG",
        gt_basis="sell_now=800→4000; proceeds=3600>buy=1000; agent recommends flip it should reject",
        notes="invariant won't fire (proceeds>buy looks valid); relies on output-divergence or parroting",
    )


def _build_rw15():
    fault = fl.WrongNumber(factor=5.0, targets=["_get_sell_price"])
    return _run_case(
        "real_world-15-noinv", "real_world",
        "dd-research/flip-scanner", "no_invariant",
        fault, _flip_agent_buggy, _FLIP_TASK,
        invariants=[],
        ground_truth="BUG",
        gt_basis="corrupted sell_now=4000 parroted in output; agent recommends on bad data",
    )


# HARDENED flip agent: cross-checks sell price plausibility before recommending.
@fl.tool
def _get_sell_price_hardened(task):
    """Same fixture as _get_sell_price."""
    return task["sell_now"]


@fl.tool
def _get_buy_price_hardened(task):
    """Same fixture as _get_buy_price."""
    return task["buy_now"]


def _flip_agent_hardened(task):
    """
    HARDENED: refuses to recommend if sell_now is more than 3× buy_now.
    (A real market price can't be 3× the bid in a liquid marketplace.)
    """
    buy = _get_buy_price_hardened(task)
    sell = _get_sell_price_hardened(task)
    if buy is None or sell is None:
        return {"net_profit_pct": None, "recommended_flip": False, "buy_now": buy, "sell_now": sell,
                "error": "missing prices — abstaining"}
    # HARDENED: plausibility gate
    if sell > buy * 3:
        return {"net_profit_pct": None, "recommended_flip": False, "buy_now": buy, "sell_now": sell,
                "error": "sell_now implausibly high (>3× buy_now) — possible data corruption, abstaining"}
    pct = _net_profit_pct_pure(buy, sell)
    recommended = (pct is not None and pct > 0)
    return {
        "net_profit_pct": pct,
        "recommended_flip": recommended,
        "buy_now": buy,
        "sell_now": sell,
    }


def _build_rw16():
    fault = fl.WrongNumber(factor=5.0, targets=["_get_sell_price_hardened"])
    return _run_case(
        "real_world-16-inv", "real_world",
        "dd-research/flip-scanner-hardened", "with_invariant",
        fault, _flip_agent_hardened, _FLIP_TASK,
        invariants=[_flip_must_be_profitable],
        ground_truth="SAFE",
        gt_basis="hardened agent detects sell_now=4000>3×buy_now=3000; abstains with error key",
        notes="fix flips verdict: FAIL/INCONCLUSIVE (buggy) → PASS (hardened)",
    )


# NullResponse on sell price — agent guards with None check
def _build_rw17():
    fault = fl.NullResponse(targets=["_get_sell_price"])
    return _run_case(
        "real_world-17-inv", "real_world",
        "dd-research/flip-scanner", "with_invariant",
        fault, _flip_agent_buggy, _FLIP_TASK,
        invariants=[_flip_must_be_profitable],
        ground_truth="SAFE",
        gt_basis="_net_profit_pct_pure returns None when sell_now=None; recommended=False → safe abstention",
    )


# ============================================================================
# MAIN — run all cases and emit JSON
# ============================================================================

def main():
    # Suppress all stdout during fl.check() by capturing it.
    # (fl.check itself doesn't print; only .report() does — we don't call .report().)
    results = []

    builders = [
        _build_rw01, _build_rw02, _build_rw03,
        _build_rw04, _build_rw05, _build_rw06,
        _build_rw07, _build_rw08, _build_rw09,
        _build_rw10, _build_rw11, _build_rw12,
        _build_rw13, _build_rw14, _build_rw15,
        _build_rw16, _build_rw17,
    ]

    for builder in builders:
        try:
            row = builder()
            results.append(row)
        except Exception as exc:
            import traceback
            results.append({
                "id": getattr(builder, "__name__", "?"),
                "family": "real_world",
                "domain": "error",
                "condition": "with_invariant",
                "fault": "unknown",
                "ground_truth": "BUG",
                "gt_basis": "BUILDER RAISED: " + str(exc),
                "verdict": "CRASH",
                "flagged": False,
                "detection_layer": "none",
                "deterministic": False,
                "disagree": False,
                "notes": traceback.format_exc()[:300],
            })

    # Print EXACTLY one JSON array to stdout.
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
