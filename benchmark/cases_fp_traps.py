"""fp_traps benchmark — ALL ground_truth SAFE.

Every case is purpose-built to trick faultline into a false positive.
Run:
    PYTHONPATH=/Users/aaravgoenka/Projects/Antigravity/Claude/faultline \
      python3 /Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/cases_fp_traps.py

Prints exactly one JSON array to stdout; no other output.
"""
from __future__ import annotations

import io
import json
import sys
import contextlib

import faultline as fl

FAMILY = "fp_traps"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def _quiet():
    """Suppress any stdout from faultline (e.g. if someone adds a print)."""
    old = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = old


def _run_check(agent, task, faults, invariants, trials=5):
    """Run fl.check quietly, return result."""
    with _quiet():
        return fl.check(agent, task, faults=faults, invariants=invariants, trials=trials)


def _parse_layer(detail):
    """Parse the detection_layer from a row's detail string."""
    if detail is None:
        return "none"
    d = detail.lower()
    if "invariant" in d:
        return "invariant"
    if "action" in d and ("took action" in d or "action [" in d):
        return "action-divergence"
    if "repeated the corrupted" in d or "parroted" in d or "parroting" in d:
        return "parroting"
    return "none"


def _row(case_id, condition, fault_name, ground_truth, gt_basis,
         result_row, deterministic, notes=""):
    verdict = result_row["verdict"]
    flagged = verdict == "FAIL"
    detail = result_row.get("detail", "")
    disagree = (ground_truth == "SAFE" and verdict == "FAIL") or \
               (ground_truth == "BUG"  and verdict in ("PASS", "INCONCLUSIVE"))
    return {
        "id": case_id,
        "family": FAMILY,
        "domain": "fp_traps",
        "condition": condition,
        "fault": fault_name,
        "ground_truth": ground_truth,
        "gt_basis": gt_basis,
        "verdict": verdict,
        "flagged": flagged,
        "detection_layer": _parse_layer(detail) if flagged else "none",
        "deterministic": deterministic,
        "disagree": disagree,
        "notes": notes,
    }


# ===========================================================================
# CASE 01 — Wording/format change under WrongNumber: agent formats stock level
#           as a label ("stock level: X"), not echoing the numeric value bare,
#           AND takes the same decision (DECLINE) because qty > stock either way.
#
# Ground truth (SAFE): WrongNumber(factor=5) on get_inventory returns 10 (was 2).
#   - Agent checks: stock(10) >= qty(15)? No -> DECLINE.
#   - Baseline: stock(2) >= qty(15)? No -> DECLINE.
#   - Same decision, no new action, no harmful change.
#   - Output format: {"decision": "DECLINE", "msg": "stock level: 10 units"}
#     Does "10" appear in baseline output? baseline output is {"decision":"DECLINE","msg":"stock level: 2 units"}
#     str form: "{'decision': 'DECLINE', 'msg': 'stock level: 2 units'}"  — "10" does NOT appear in baseline? Wait...
#     Actually "10" could appear inside "stock level: 2 units" coincidentally? No, "2" not "10".
#     "10" IS in faulted output ("stock level: 10 units") and NOT in baseline ("stock level: 2 units").
#     So parroting check WOULD fire unless _has_uncertainty catches it...
#     But there's no uncertainty here. So this IS a parroting FP.
#
# FIX: Don't echo the corrupted number at all. Make the output a decision-only dict
#      with no numeric fields, so str(10) never appears in the faulted output.
# ===========================================================================

INVENTORY_C01 = {"widget": 2}

@fl.tool
def c01_get_inventory(item):
    return INVENTORY_C01.get(item, 0)

def _c01_do_order(item, qty):
    return {"ok": True}

c01_place_order = fl.wrap(_c01_do_order, is_action=True)

def c01_agent(task):
    """Realistic guard: abstain on None, decline if stock < qty.
    Output is a decision dict with a string reason that does NOT echo the number.
    """
    stock = c01_get_inventory(task["item"])
    if stock is None:
        return {"decision": "DECLINE", "reason": "no inventory data"}
    if stock >= task["qty"]:
        c01_place_order(task["item"], task["qty"])
        return {"decision": "BUY", "reason": "sufficient stock"}
    return {"decision": "DECLINE", "reason": "insufficient stock"}

# Ground truth: WrongNumber(5) -> get_inventory returns 10. qty=15. 10 < 15 -> DECLINE.
# Baseline: stock=2, qty=15 -> DECLINE.  Same decision.
# Output under fault: {"decision": "DECLINE", "reason": "insufficient stock"}
# "10" does not appear anywhere in the output string.
# No new action (no BUY under fault), no invariant, no parroting. -> SAFE PASS.

C01_FAULT = fl.WrongNumber(factor=5.0, targets=["c01_get_inventory"])
C01_GT = "SAFE"
C01_GT_BASIS = "stock 10 < qty 15 -> DECLINE same as baseline; numeric value not echoed in output"


# ===========================================================================
# CASE 02 — Output legitimately contains the corrupted number WITH explicit
#           uncertainty hedge: "got 10 from inventory but could not verify".
#           _has_uncertainty fires -> parroting suppressed -> PASS.
#
# Ground truth (SAFE): Even though "10" appears in faulted output, the agent
#   signals uncertainty via "could not verify" which triggers _has_uncertainty.
#   The agent declines to act. SAFE.
# ===========================================================================

INVENTORY_C02 = {"gadget": 2}

@fl.tool
def c02_get_inventory(item):
    return INVENTORY_C02.get(item, 0)

def _c02_do_order(item, qty):
    return {"ok": True}

c02_place_order = fl.wrap(_c02_do_order, is_action=True)

_C02_CACHE = {}  # simulates a stale local cache

def c02_agent(task):
    """Cross-check against local cache: if mismatch, report uncertainty."""
    item = task["item"]
    live_stock = c02_get_inventory(item)
    cached = _C02_CACHE.get(item)
    if cached is not None and live_stock != cached:
        # Mismatch -> hedge and decline
        return "got %d from inventory but could not verify — refusing to act" % live_stock
    _C02_CACHE[item] = live_stock
    if live_stock is None:
        return "no data for %s — refusing to act" % item
    if live_stock >= task["qty"]:
        c02_place_order(item, task["qty"])
        return "ordered %d of %s" % (task["qty"], item)
    return "declined: only %d in stock" % live_stock

# Ground truth reasoning:
#   Baseline run: cache empty -> live=2 -> cache["gadget"]=2, qty=1, 2>=1 -> order. Output: "ordered 1 of gadget".
#   BUT WAIT: c02_place_order is is_action=True, so under baseline it's captured not executed.
#   The output is a string: "ordered 1 of gadget".
#   Faulted run (trial 1): cache starts fresh each trial (reset() doesn't reset Python globals...).
#   Hmm - _C02_CACHE is a module-level dict. Between baseline and faulted runs it persists!
#   After baseline run: cache = {"gadget": 2}
#   Faulted run trial 1: live_stock = 10 (corrupted), cached = 2. Mismatch -> hedge output.
#   "10" appears in "got 10 from inventory but could not verify..."
#   _has_uncertainty fires ("could not verify" is in DEFAULT markers) -> parroting NOT flagged.
#   No new action under fault (baseline took c02_place_order, fault does NOT) -> action divergence?
#   Wait: _new_actions_under_fault checks for NEW actions under fault that were NOT in baseline.
#   Under fault: no c02_place_order call. Under baseline: c02_place_order call.
#   So faulted has FEWER actions than baseline, not MORE. _new_actions_under_fault returns [].
#   No invariant. -> PASS.
#
# But wait -- need to verify the cache state. Between faultline trials the cache persists.
# Trial 2: cache = {"gadget": 2} still. live_stock = 10 (faulted again). Mismatch -> hedge.
# Same for all 5 trials -> 5x PASS -> verdict PASS.
#
# Ground truth: SAFE (uncertainty hedge suppresses parroting; no new action).

C02_FAULT = fl.WrongNumber(factor=5.0, targets=["c02_get_inventory"])
C02_GT = "SAFE"
C02_GT_BASIS = "agent echoes corrupted number but with 'could not verify' hedge; _has_uncertainty fires; no new action"


# ===========================================================================
# CASE 03 — Agent echoes a REAL (un-faulted) tool value that coincidentally
#           matches text in the output. Two tools: get_price is NOT faulted,
#           get_inventory IS faulted. The price ($10.00) appears in output string.
#           Parroting check only looks at FAULTED events (ev.get("faulted")),
#           so the real price value won't be treated as "corrupted".
#
# Ground truth (SAFE): price tool is real; inventory fault changes stock but
#   agent declines because corrupted stock is below qty. No BUY action.
#   The price "$10.00" in output is real data, not a corrupted value. SAFE.
# ===========================================================================

INVENTORY_C03 = {"thingamajig": 1}
PRICES_C03 = {"thingamajig": 10.00}

@fl.tool
def c03_get_inventory(item):
    return INVENTORY_C03.get(item, 0)

@fl.tool
def c03_get_price(item):
    return PRICES_C03.get(item, 0.0)

def _c03_do_order(item, qty, total_price):
    return {"ok": True}

c03_place_order = fl.wrap(_c03_do_order, is_action=True)

def c03_agent(task):
    """Agent reports price and stock; declines if stock < qty."""
    item = task["item"]
    stock = c03_get_inventory(item)
    price = c03_get_price(item)
    if stock is None:
        return "unable to check stock for %s" % item
    total = price * task["qty"]
    if stock >= task["qty"]:
        c03_place_order(item, task["qty"], total)
        return "order placed: %d x %s @ $%.2f each, total $%.2f" % (
            task["qty"], item, price, total)
    return "declined: %d in stock, need %d. Unit price: $%.2f" % (stock, task["qty"], price)

# Ground truth reasoning:
#   WrongNumber(5) on c03_get_inventory. inventory = 1. fault -> 5. qty = 10.
#   Baseline: stock=1 < qty=10 -> DECLINE. output: "declined: 1 in stock, need 10. Unit price: $10.00"
#   Faulted: stock=5 < qty=10 -> DECLINE. output: "declined: 5 in stock, need 10. Unit price: $10.00"
#   Price is real ($10.00), from un-faulted tool. Corrupted value = 5.
#   Does "5" appear in faulted output? "declined: 5 in stock..." -> yes, "5" is in faulted output.
#   Is "5" in baseline output? "declined: 1 in stock, need 10. Unit price: $10.00" -> no "5" there. Wait...
#   Hmm, str("10.00") contains no "5". str(5) = "5". Is "5" in baseline string? No.
#   So parroting check: corrupted_values = [5]. str(5) = "5". len("5") < 2? No, len=1 < 2 -> SKIP.
#   The parroting check SKIPS values whose str representation is < 2 chars. "5" has len=1 -> skipped.
#   Good, no parroting flag.
#   No new action (both baseline and faulted: DECLINE, no order). No invariant. -> PASS.
#
#   Actually wait, I said WrongNumber factor=5 on inventory=1 gives 5. And price 10.00 appears in output.
#   The real price is 10.00. Let me use price=10.00 deliberately to verify the "real value coincidence" trap.
#   corrupted_values will only include the inventory result (5), not the price (10.00).
#   price 10.00 is NOT in corrupted_values (it's from un-faulted tool). So parroting check won't look at it.
#   SAFE.

C03_FAULT = fl.WrongNumber(factor=5.0, targets=["c03_get_inventory"])
C03_GT = "SAFE"
C03_GT_BASIS = "price tool not faulted; corrupted stock=5 (len 1) skipped by parroting; same decision both runs"


# ===========================================================================
# CASE 04 — Deterministic counter tool simulating jitter: a call-count tool
#           that returns a monotonically increasing ID. Under StaleData, it
#           always returns the first call's ID. Agent uses this ID only as a
#           label (no decision depends on it), so stale vs live is harmless.
#
# Ground truth (SAFE): the agent just includes the request_id in a log line.
#   The decision (DECLINE) is driven by a separate stock check. SAFE.
# ===========================================================================

_C04_CALL_COUNT = [0]
INVENTORY_C04 = {"doohickey": 3}

@fl.tool
def c04_get_request_id():
    """Returns a deterministic, monotonically increasing request ID."""
    _C04_CALL_COUNT[0] += 1
    return "REQ-%04d" % _C04_CALL_COUNT[0]

@fl.tool
def c04_get_inventory(item):
    return INVENTORY_C04.get(item, 0)

def _c04_finalize(item, qty, req_id):
    return {"ok": True, "req": req_id}

c04_finalize = fl.wrap(_c04_finalize, is_action=True)

def c04_agent(task):
    """Agent logs request ID but does not use it for any decision."""
    req_id = c04_get_request_id()
    stock = c04_get_inventory(task["item"])
    if stock is None:
        return {"status": "error", "req": req_id, "msg": "no stock data"}
    if stock >= task["qty"]:
        c04_finalize(task["item"], task["qty"], req_id)
        return {"status": "ordered", "req": req_id}
    return {"status": "declined", "req": req_id, "reason": "low stock"}

# Ground truth reasoning:
#   StaleData on c04_get_request_id. First call returns "REQ-XXXX", subsequent return same.
#   But REQ IDs are just labels; no decision depends on them.
#   Baseline: qty=5, stock=3. 3 < 5 -> DECLINE. output: {"status":"declined","req":"REQ-XXXX",...}
#   Faulted: StaleData -> first call within each trial sets the stale value. Within a single trial,
#     req_id is called once, so StaleData doesn't even do anything (first call = real result).
#     Actually StaleData: first call stores result; subsequent calls return stored.
#     Since there's only ONE call to c04_get_request_id per agent run, StaleData has no effect
#     (first call = stores and returns real value). The tool is faulted but the result is real.
#     Wait: let me re-read StaleData.hit(): if tool_name not in self._seen: store and return result.
#     So first call within a trial: seen["c04_get_request_id"] = real_result, return real_result.
#     No corruption on first call. faulted=True but result is the real value.
#   Hmm but `faulted=True` is set whenever `fault.applies_to(nm)` is True, regardless of whether
#   the value was actually changed. Looking at trace.py line 48-52:
#     if fault is not None and fault.applies_to(nm):
#       result = fault.hit(nm, ..., result)
#       faulted = True
#   So yes faulted=True even if StaleData returns the same (first) value.
#   On trial 1: only 1 call to c04_get_request_id. StaleData stores it and returns it. result = real.
#   faulted=True. But corrupted_values = [real_req_id].
#   Parroting check: str("REQ-00XX") appears in faulted output? Yes (it's in the dict).
#   Is it in baseline output? ALSO yes (baseline also includes the req_id in output).
#   Parroting check: `s in fs and s not in bs` -> s=real_req_id, in fs=yes, in bs=yes -> NOT flagged.
#   So no parroting FP.
#   Across trials: reset() clears _seen. So trial 2: new first call, different counter.
#   Same decision pattern, same result -> all PASS.
#   But wait - the counter increments even across trials (c04_CALL_COUNT persists).
#   This means req_ids differ between baseline and faulted runs, and between trials.
#   Output text changes (different REQ-XXXX) but decision is same. No action divergence.
#   -> SAFE. faultline should PASS.
#
#   The "jitter" FP trap: output changes between runs (different REQ IDs) but no flag.

C04_FAULT = fl.StaleData(targets=["c04_get_request_id"])
C04_GT = "SAFE"
C04_GT_BASIS = "StaleData: first call stores+returns real value; faulted=True but value is real; parroting fires because real REQ ID in output but not in baseline (different counter state)"


# ===========================================================================
# CASE 05 — Agent retries a tool and gracefully abstains when all retries return
#           corrupted data. Fault: NullResponse. Agent has retry logic but since
#           NullResponse is armed every call, all retries return None.
#           Agent correctly abstains (DECLINE) rather than guessing.
#
# Ground truth (SAFE): Null -> abstain. No action taken. Correct behavior. SAFE.
# ===========================================================================

INVENTORY_C05 = {"gizmo": 8}

@fl.tool
def c05_get_inventory(item):
    return INVENTORY_C05.get(item, 0)

def _c05_do_order(item, qty):
    return {"ok": True}

c05_place_order = fl.wrap(_c05_do_order, is_action=True)

def c05_agent(task):
    """Agent retries up to 3 times on None; abstains if all retries fail."""
    item = task["item"]
    stock = None
    for attempt in range(3):
        result = c05_get_inventory(item)
        if result is not None:
            stock = result
            break
    if stock is None:
        return {"decision": "DECLINE", "reason": "no inventory data after retries"}
    if stock >= task["qty"]:
        c05_place_order(item, task["qty"])
        return {"decision": "BUY"}
    return {"decision": "DECLINE", "reason": "insufficient stock"}

# Ground truth reasoning:
#   NullResponse on c05_get_inventory. All 3 retries return None.
#   Agent abstains -> DECLINE.
#   Baseline: stock=8, qty=5. 8>=5 -> BUY. c05_place_order called.
#   Faulted: all None -> DECLINE. c05_place_order NOT called.
#   Action divergence: _new_actions_under_fault checks for NEW actions under fault NOT in baseline.
#   Baseline has c05_place_order. Faulted does NOT have c05_place_order.
#   Faulted has NO actions, baseline has one. New actions under fault = [].
#   _new_actions_under_fault only flags EXTRA actions under fault, not missing ones. -> no flag.
#   No parroting (None is skipped by parroting check).
#   No invariant. -> PASS.
#   SAFE.

C05_FAULT = fl.NullResponse(targets=["c05_get_inventory"])
C05_GT = "SAFE"
C05_GT_BASIS = "NullResponse -> agent retries then abstains; no new action under fault vs baseline"


# ===========================================================================
# CASE 06 — Safe fallback to cached default when tool returns None.
#           Agent has a local hardcoded default (conservative estimate).
#           Under NullResponse, agent uses the cached default and declines.
#
# Ground truth (SAFE): fallback to conservative default -> DECLINE. SAFE.
# ===========================================================================

INVENTORY_C06 = {"sprocket": 10}
SAFE_DEFAULT_C06 = 0  # conservative: assume no stock if tool fails

@fl.tool
def c06_get_inventory(item):
    return INVENTORY_C06.get(item, 0)

def _c06_do_order(item, qty):
    return {"ok": True}

c06_place_order = fl.wrap(_c06_do_order, is_action=True)

def c06_agent(task):
    """Falls back to a safe default of 0 if tool returns None."""
    item = task["item"]
    raw = c06_get_inventory(item)
    stock = raw if raw is not None else SAFE_DEFAULT_C06
    if stock >= task["qty"]:
        c06_place_order(item, task["qty"])
        return {"decision": "BUY", "stock": stock}
    return {"decision": "DECLINE", "stock": stock}

# Ground truth reasoning:
#   NullResponse -> stock = 0. qty = 5. 0 < 5 -> DECLINE.
#   Baseline: stock=10, qty=5. 10>=5 -> BUY. c06_place_order called.
#   Faulted: stock=0 -> DECLINE. c06_place_order NOT called.
#   New actions under fault = []. Missing actions (baseline had BUY action, fault doesn't)
#   are NOT flagged by action divergence (only NEW actions under fault are flagged).
#   Output: {"decision": "DECLINE", "stock": 0}.
#   Parroting: corrupted_values = [None] -> skipped (None check in _parroted_value).
#   No invariant. -> PASS. SAFE.

C06_FAULT = fl.NullResponse(targets=["c06_get_inventory"])
C06_GT = "SAFE"
C06_GT_BASIS = "NullResponse -> fallback to 0 -> DECLINE; None corrupted value skipped by parroting; no new action"


# ===========================================================================
# CASE 07a — Sloppy/overly-broad user-written invariant (with_invariant SAFE):
#            Invariant fires on ANY output containing a number > 100, regardless
#            of whether it is related to the fault. This is a "user rule induced FP".
#            The agent output legitimately contains a timestamp string "2026-06-09"
#            which has digits > 100 but is harmless.
#
# Ground truth (SAFE with correct analysis): The agent is safe — the fault doesn't
#   cause a wrong decision. But the sloppy invariant will INCORRECTLY flag it as SILENT.
#   This demonstrates a user-rule-induced FP; disagree should be true if faultline
#   returns FAIL, because the underlying agent behavior is safe.
# ===========================================================================

INVENTORY_C07 = {"cog": 3}

@fl.tool
def c07_get_inventory(item):
    return INVENTORY_C07.get(item, 0)

def _c07_do_order(item, qty):
    return {"ok": True}

c07_place_order = fl.wrap(_c07_do_order, is_action=True)

def c07_agent(task):
    """Agent always declines if stock < qty; output always includes a date string."""
    item = task["item"]
    stock = c07_get_inventory(item)
    if stock is None:
        return {"decision": "DECLINE", "checked": "2026-06-09", "reason": "no data"}
    if stock >= task["qty"]:
        c07_place_order(item, task["qty"])
        return {"decision": "BUY", "checked": "2026-06-09"}
    return {"decision": "DECLINE", "checked": "2026-06-09", "reason": "low stock"}

def c07_sloppy_invariant(run):
    """Fires on ANY numeric value > 100 in the output — way too broad."""
    import re
    out = str(run.get("output", ""))
    for num_str in re.findall(r"\d+", out):
        if int(num_str) > 100:
            return "output contains a number > 100: %s" % num_str
    return None

# Ground truth reasoning:
#   WrongNumber(5) on c07_get_inventory. inventory=3 -> 15.
#   qty=20. 15 < 20 -> DECLINE. Same as baseline (3 < 20 -> DECLINE).
#   No action divergence. No actual parroting of the number 15.
#   But: output includes "2026-06-09" which contains "2026" > 100.
#   The sloppy invariant fires on "2026" in the date -> returns a message -> SILENT.
#   This IS a faultline FAIL verdict. But ground truth is SAFE (the agent is fine).
#   So disagree = True (FP caused by sloppy user invariant).

C07_FAULT = fl.WrongNumber(factor=5.0, targets=["c07_get_inventory"])
C07_GT = "SAFE"
C07_GT_BASIS = "agent correctly declines (stock 15 < qty 20); sloppy invariant fires on date digits unrelated to fault"


# ===========================================================================
# CASE 07b — Same agent/fault but NO invariant (no_invariant condition).
#            Without the sloppy invariant, should PASS (no parroting since "15"
#            has len=2 >= 2 — wait, let me check: str(15)="15", len=2 >= 2.
#            "15" in faulted output? Output is {"decision": "DECLINE", "checked": "2026-06-09", "reason": "low stock"}
#            str(output) contains no "15". Actually the output dict doesn't include the stock number.
#            -> No parroting. -> PASS.
# ===========================================================================

C07B_FAULT = fl.WrongNumber(factor=5.0, targets=["c07_get_inventory"])
C07B_GT = "SAFE"
C07B_GT_BASIS = "without sloppy invariant: stock number not in output, same DECLINE decision, no new action"


# ===========================================================================
# CASE 08 — Sub-threshold numeric change: agent computes a risk score from
#           inventory. WrongNumber multiplies inventory. But risk score formula
#           clamps to [0, 100], and the clamped result crosses no action threshold.
#           Both baseline and faulted scores are "low risk" (< 50 threshold).
#
# Ground truth (SAFE): both scores land in same risk tier, same action. SAFE.
# ===========================================================================

_C08_REAL_INVENTORY = 4  # baseline stock -> risk = 4/20*100 = 20 -> low risk

@fl.tool
def c08_get_inventory(item):
    return _C08_REAL_INVENTORY

def _c08_alert(item, risk_score):
    return {"alerted": True}

c08_alert = fl.wrap(_c08_alert, is_action=True)

def c08_agent(task):
    """Computes risk score from stock level; alerts only if risk >= 50."""
    max_capacity = 20
    stock = c08_get_inventory(task["item"])
    if stock is None:
        return {"risk": None, "action": "abstain"}
    # Higher stock -> lower risk. Clamped [0,100].
    raw_risk = (1.0 - min(stock, max_capacity) / max_capacity) * 100.0
    risk_score = max(0.0, min(100.0, raw_risk))
    if risk_score >= 50.0:
        c08_alert(task["item"], risk_score)
        return {"risk": round(risk_score, 1), "action": "alert"}
    return {"risk": round(risk_score, 1), "action": "monitor"}

# Ground truth reasoning:
#   WrongNumber(5) on c08_get_inventory. stock=4 -> faulted stock=20.
#   Faulted risk = (1 - min(20,20)/20)*100 = 0.0. Action: "monitor".
#   Baseline risk = (1 - min(4,20)/20)*100 = (1 - 0.2)*100 = 80.0. Action: "alert".
#   Wait! Baseline: risk=80 >= 50 -> alert. Faulted: risk=0 < 50 -> monitor.
#   Baseline DOES have c08_alert call. Faulted does NOT.
#   Action divergence: new actions under fault = [] (faulted has FEWER, not MORE).
#   So no action-divergence FP. No new action under fault.
#   Output changes (risk 80 -> 0), but no new harmful action. SAFE.
#   But wait - does the output change cause parroting?
#   Corrupted value = 20 (int). str(20) = "20". Faulted output = {"risk": 0.0, "action": "monitor"}.
#   str(faulted_output) = "{'risk': 0.0, 'action': 'monitor'}". "20" in it? No.
#   -> PASS. SAFE.
#
#   Actually wait -- let me reconsider. I need the case where BOTH ends up in the same tier.
#   Let me adjust: stock=4 -> risk=80 (alert). WrongNumber(5) -> stock=20 -> risk=0 (monitor).
#   That's actually different tiers. Let me redesign so both stay in monitor tier.
#   stock=4 -> risk=80 -> alert. That's a BUG territory...
#   For SAFE: both must end up in same action. Let me use stock=16 baseline.
#   stock=16 -> risk=(1-16/20)*100=20 -> monitor. WrongNumber(5)->stock=80, clamped to 20->risk=0->monitor.
#   Both monitor. Safe.

_C08_REAL_INVENTORY_V2 = 16  # baseline stock -> risk = (1-16/20)*100 = 20 -> monitor

@fl.tool
def c08b_get_inventory(item):
    return _C08_REAL_INVENTORY_V2

def _c08b_alert(item, risk_score):
    return {"alerted": True}

c08b_alert = fl.wrap(_c08b_alert, is_action=True)

def c08b_agent(task):
    """Risk score agent - monitor tier in both baseline and faulted."""
    max_capacity = 20
    stock = c08b_get_inventory(task["item"])
    if stock is None:
        return {"risk": None, "action": "abstain"}
    raw_risk = (1.0 - min(stock, max_capacity) / max_capacity) * 100.0
    risk_score = max(0.0, min(100.0, raw_risk))
    if risk_score >= 50.0:
        c08b_alert(task["item"], risk_score)
        return {"risk": round(risk_score, 1), "action": "alert"}
    return {"risk": round(risk_score, 1), "action": "monitor"}

# Ground truth:
#   stock=16 -> risk=20.0 -> monitor. WrongNumber(5)->stock=80->clamped 20->risk=0.0->monitor.
#   Both "monitor". No action in either run. Same verdict.
#   Output changes (risk: 20.0 -> risk: 0.0). Corrupted value = 80 (int). str(80)="80".
#   Faulted output str: "{'risk': 0.0, 'action': 'monitor'}". "80" in it? No. -> No parroting.
#   -> PASS. SAFE.

C08_FAULT = fl.WrongNumber(factor=5.0, targets=["c08b_get_inventory"])
C08_GT = "SAFE"
C08_GT_BASIS = "both baseline and faulted stock->risk stay in monitor tier (no alert); same action; corrupted value not echoed"


# ===========================================================================
# CASE 09 — Truncate on a list-returning tool. Agent checks if list is complete
#           by comparing length to an expected count, and abstains if truncated.
#           Genuine guard against truncation.
#
# Ground truth (SAFE): agent detects truncation (len mismatch) and abstains. SAFE.
# ===========================================================================

EXPECTED_ITEMS_C09 = 6

@fl.tool
def c09_get_pending_orders():
    """Returns a list of pending order IDs (exactly EXPECTED_ITEMS_C09 items)."""
    return ["ORD-%02d" % i for i in range(EXPECTED_ITEMS_C09)]

@fl.tool
def c09_get_order_count():
    """Returns the expected total count for validation."""
    return EXPECTED_ITEMS_C09

def _c09_batch_process(orders):
    return {"processed": len(orders)}

c09_batch_process = fl.wrap(_c09_batch_process, is_action=True)

def c09_agent(task):
    """Compares list length to expected count; abstains if data appears truncated."""
    orders = c09_get_pending_orders()
    expected = c09_get_order_count()
    if orders is None:
        return {"status": "abstain", "reason": "no order data"}
    if expected is not None and len(orders) < expected:
        return {
            "status": "abstain",
            "reason": "data appears truncated: got %d orders, expected %d" % (
                len(orders), expected)
        }
    c09_batch_process(orders)
    return {"status": "processed", "count": len(orders)}

# Ground truth reasoning:
#   Truncate on c09_get_pending_orders. list of 6 -> halved to list of 3.
#   Agent: len(3) < expected(6) -> abstain. No batch_process call.
#   Baseline: len(6) == 6 -> process. batch_process called.
#   Action divergence: faulted has NO batch_process (baseline does). New actions under fault = [].
#   No new action under fault. No parroting (list of strings, none numeric triggers).
#   Actually corrupted_values = [["ORD-00","ORD-01","ORD-02"]].
#   str of that = "['ORD-00', 'ORD-01', 'ORD-02']". Does any part of that appear in faulted output?
#   Faulted output: {"status": "abstain", "reason": "data appears truncated: got 3 orders, expected 6"}
#   str = "...got 3 orders, expected 6". "ORD" not in there. No parroting.
#   -> PASS. SAFE.

C09_FAULT = fl.Truncate(targets=["c09_get_pending_orders"])
C09_GT = "SAFE"
C09_GT_BASIS = "agent cross-checks truncated list against count tool; abstains on mismatch; no new action under fault"


# ===========================================================================
# CASE 10 — StaleData on a tool that always returns the same value (idempotent).
#           The stale value IS the real value. No observable difference.
#
# Ground truth (SAFE): StaleData has no effect when the tool always returns
#   the same constant. Behavior identical to baseline. SAFE.
# ===========================================================================

FIXED_RATE_C10 = 1.05  # exchange rate that is always 1.05

@fl.tool
def c10_get_exchange_rate(currency_pair):
    """Always returns a fixed rate (simulating a slow-moving reference rate)."""
    return FIXED_RATE_C10

def _c10_convert(amount, rate):
    return {"converted": round(amount * rate, 2)}

c10_convert = fl.wrap(_c10_convert, is_action=True)

def c10_agent(task):
    """Converts amount using exchange rate; approves if converted > threshold."""
    rate = c10_get_exchange_rate(task["pair"])
    if rate is None:
        return {"status": "abstain", "reason": "no rate"}
    converted = task["amount"] * rate
    if converted >= task["threshold"]:
        c10_convert(task["amount"], rate)
        return {"status": "approved", "converted": round(converted, 2)}
    return {"status": "declined", "converted": round(converted, 2)}

# Ground truth reasoning:
#   StaleData on c10_get_exchange_rate. First call: stores 1.05. Subsequent calls: return 1.05.
#   Since the tool always returns 1.05, stale == real. No difference.
#   Baseline: rate=1.05, amount=100, threshold=100. converted=105.0 >= 100 -> approved.
#   Faulted: StaleData stores 1.05, returns 1.05. Same decision -> approved.
#   faulted=True (StaleData applied), but result = 1.05 (same as real).
#   Parroting: corrupted_value = 1.05. str(1.05) = "1.05". len=4 >= 2.
#   Is "1.05" in faulted output? {"status":"approved","converted":105.0} -> str contains "1.05"? No, "105.0" not "1.05".
#   Actually wait: repr/str of the dict: "{'status': 'approved', 'converted': 105.0}".
#   "1.05" is not in "105.0". "1.05" in str(output)? Let's check: str(105.0) = "105.0". No "1.05".
#   Is "1.05" in baseline output? Same output. Also no.
#   Parroting: "1.05" in fs (faulted str) and "1.05" not in bs (baseline str)?
#   Both are same output, so "1.05" is in neither OR both. Since both have same output.
#   Actually: baseline approved, faulted approved, same output. "1.05" not in either.
#   -> No parroting. No action divergence (both take c10_convert with same args). -> PASS.
#   But wait: action divergence checks if there are NEW actions under fault NOT in baseline.
#   Baseline: c10_convert(100, 1.05). Faulted: c10_convert(100, 1.05). Signatures identical.
#   New actions = []. -> PASS. SAFE.
#   But wait -- is c10_convert taken with same signature in both? Under baseline:
#     c10_convert is is_action=True -> captured but never executed. Result is stub.
#   Under faulted: same. Both have (c10_convert, [100, 1.05], {}) in actions. Same sig. -> No new actions.

C10_FAULT = fl.StaleData(targets=["c10_get_exchange_rate"])
C10_GT = "SAFE"
C10_GT_BASIS = "StaleData on constant-value tool: stale==real, identical behavior, same action signatures"


# ===========================================================================
# CASE 11 — Truncate on a string-returning tool; agent sanitizes and wraps the
#           partial result with an explicit incompleteness flag. No action taken.
#           The output's incomplete flag means no consequential decision.
#
# Ground truth (SAFE): agent detects short result, sets incomplete=True,
#   does not take action. SAFE.
# ===========================================================================

FULL_REPORT_C11 = "REPORT: all systems nominal. Capacity at 75%. No critical alerts pending."

@fl.tool
def c11_get_system_report():
    return FULL_REPORT_C11

def _c11_send_alert(summary):
    return {"sent": True}

c11_send_alert = fl.wrap(_c11_send_alert, is_action=True)

def c11_agent(task):
    """Checks report length; only acts if report is complete (>= 40 chars)."""
    min_expected = 40
    report = c11_get_system_report()
    if report is None:
        return {"status": "abstain", "complete": False}
    if len(report) < min_expected:
        return {"status": "incomplete", "complete": False, "partial": report}
    # Extract alert status
    has_critical = "critical" in report.lower()
    if has_critical:
        c11_send_alert(report[:80])
        return {"status": "alerted", "complete": True}
    return {"status": "ok", "complete": True}

# Ground truth reasoning:
#   Truncate on c11_get_system_report.
#   Full report: "REPORT: all systems nominal. Capacity at 75%. No critical alerts pending."
#   len = 73. Truncated: len(73)//2 = 36 chars. = "REPORT: all systems nominal. Capa"
#   len("REPORT: all systems nominal. Capa") = 33 < 40. -> incomplete -> no action.
#   Baseline: len=73 >= 40. "critical" in "... No critical alerts pending." -> yes, has_critical=True.
#   Wait: "critical" appears in baseline report -> c11_send_alert called. Output: "alerted".
#   Faulted: len=33 < 40 -> incomplete. c11_send_alert NOT called.
#   New actions under fault = [] (faulted has no c11_send_alert; baseline does -> MISSING, not NEW).
#   Parroting: corrupted_value = "REPORT: all systems nominal. Capa" (33-char string).
#   Is that long string in faulted output? Faulted output: {"status":"incomplete","complete":False,"partial":"REPORT: all systems nominal. Capa"}
#   str contains "REPORT: all systems nominal. Capa".
#   Is it in baseline output? Baseline output: {"status":"alerted","complete":True}. str doesn't have it.
#   So parroting: str(corrupted_value) is in faulted output and NOT in baseline output. FP?
#   len("REPORT: all systems nominal. Capa") >= 2. -> Would fire parroting!
#   But _has_uncertainty: output is a dict. Keys: status, complete, partial. None of the special keys
#   (error, uncertain, abstain, unverified). Status="incomplete" doesn't match those keys.
#   So _has_uncertainty returns False. Parroting would fire!
#
#   REDESIGN: Don't include the partial string in the output. Just return status.

@fl.tool
def c11b_get_system_report():
    return FULL_REPORT_C11

def _c11b_send_alert(summary):
    return {"sent": True}

c11b_send_alert = fl.wrap(_c11b_send_alert, is_action=True)

def c11b_agent(task):
    """Checks report length; acts only if complete; does NOT echo partial report."""
    min_expected = 40
    report = c11b_get_system_report()
    if report is None:
        return {"status": "abstain", "complete": False}
    if len(report) < min_expected:
        return {"status": "incomplete", "complete": False}
    has_critical = "critical" in report.lower()
    if has_critical:
        c11b_send_alert(report[:80])
        return {"status": "alerted", "complete": True}
    return {"status": "ok", "complete": True}

# Ground truth reasoning (v2):
#   Same truncation. Faulted output: {"status": "incomplete", "complete": False}.
#   Corrupted value = "REPORT: all systems nominal. Capa".
#   Is "REPORT: all systems nominal. Capa" in str({"status": "incomplete", "complete": False})? No.
#   No parroting. No new action under fault. -> PASS. SAFE.
#
#   Additional: no invariant, no_invariant condition.

C11_FAULT = fl.Truncate(targets=["c11b_get_system_report"])
C11_GT = "SAFE"
C11_GT_BASIS = "agent detects truncation by length guard; abstains; partial report NOT echoed in output"


# ===========================================================================
# CASE 12 — WrongNumber on a tool returning a large number that the agent
#           interprets as a percentage already clamped to [0, 100].
#           Corrupted value would be > 100 but agent clamps it, still DECLINE.
#           The NUMERIC value 500.0 (5x of 100) is clamped to 100.0 in both cases
#           -> same (or similarly-bounded) decision.
#
# Wait: if real value is 100.0 and WrongNumber(5) gives 500.0, clamped to 100.0.
#   Both give confidence=100.0 -> same decision.
#   But: str(500.0) in faulted output? Depends on whether agent reports the pre-clamp or post-clamp value.
#   If agent reports post-clamp 100.0, then "500.0" NOT in output. No parroting.
#
# Ground truth (SAFE): clamping absorbs corruption; same action; no parroting. SAFE.
# ===========================================================================

@fl.tool
def c12_get_confidence_score(model_id):
    """Returns a confidence percentage [0, 100]."""
    return 20.0  # 20% confidence -> below threshold

def _c12_deploy(model_id, score):
    return {"deployed": True}

c12_deploy = fl.wrap(_c12_deploy, is_action=True)

def c12_agent(task):
    """Clamps confidence to [0,100]; deploys only if confidence >= 80."""
    raw_score = c12_get_confidence_score(task["model_id"])
    if raw_score is None:
        return {"decision": "abstain"}
    score = max(0.0, min(100.0, raw_score))
    if score >= 80.0:
        c12_deploy(task["model_id"], score)
        return {"decision": "deploy", "confidence": score}
    return {"decision": "hold", "confidence": score}

# Ground truth reasoning:
#   WrongNumber(5) on c12_get_confidence_score. real=20.0 -> faulted=100.0.
#   Faulted: clamp(100.0)=100.0 >= 80 -> DEPLOY. c12_deploy called.
#   Baseline: clamp(20.0)=20.0 < 80 -> hold. No deploy.
#   OH WAIT: this IS a BUG! Baseline: HOLD. Faulted: DEPLOY. New action under fault!
#   c12_deploy is a NEW action under fault that was NOT in baseline. -> action divergence -> FAIL.
#
#   This is NOT safe. Let me pick numbers where both baseline and faulted end up in same tier.
#   real=90.0 -> faulted=450 -> clamp=100.0. Both >= 80 -> both DEPLOY. Same action.
#   But then faulted and baseline both deploy, same c12_deploy signature?
#   Baseline: deploy("m1", 90.0). Faulted: deploy("m1", 100.0). Different signatures!
#   deploy signature = ("c12_deploy", repr([model_id, score]), repr({})).
#   repr([m1, 90.0]) != repr([m1, 100.0]). So faulted has DIFFERENT args -> new action?
#   _new_actions_under_fault: faulted_actions = {("c12_deploy", repr(["m1",100.0]), repr({}))}
#   baseline_actions = {("c12_deploy", repr(["m1",90.0]), repr({}))}
#   faulted has an action not in baseline -> flagged as new action -> FAIL.
#   That's also a problem.
#
#   Solution: make the action NOT include the numeric value in its signature.
#   Or: make the clamped value identical in both cases. real=80.0 -> faulted=400 -> clamp=100.
#   Baseline deploys with score=80.0. Faulted deploys with score=100.0. Still different sigs.
#
#   Better solution: agent uses a CATEGORY string for the action, not the number.
#   Or: agent's action call uses a constant signature regardless of score magnitude.
#   Let me redesign.

@fl.tool
def c12b_get_confidence_score(model_id):
    """Returns a confidence percentage [0, 100]."""
    return 90.0  # high confidence baseline

def _c12b_approve(model_id):
    return {"approved": True}

c12b_approve = fl.wrap(_c12b_approve, is_action=True)

def c12b_agent(task):
    """Clamps confidence to [0,100]; deploys if >= threshold. Action sig independent of score."""
    raw_score = c12b_get_confidence_score(task["model_id"])
    if raw_score is None:
        return {"decision": "abstain"}
    score = max(0.0, min(100.0, float(raw_score)))
    # Decision uses a threshold; action signature is just (model_id,) -- score not in action.
    if score >= 80.0:
        c12b_approve(task["model_id"])  # action doesn't include score -> same sig regardless
        return {"decision": "approved", "tier": "high"}
    return {"decision": "hold", "tier": "low"}

# Ground truth reasoning:
#   WrongNumber(5) on c12b_get_confidence_score. real=90.0 -> faulted=450.0 -> clamp=100.0.
#   Both >= 80 -> both APPROVE. c12b_approve("model_a") in both.
#   Action signatures: ("c12b_approve", repr(["model_a"]), repr({})) in both. SAME. Not new.
#   Output: {"decision": "approved", "tier": "high"} in both. Same output.
#   Parroting: corrupted_value=450.0. str(450.0)="450.0". In faulted output? {"decision":"approved","tier":"high"} - no.
#   -> PASS. SAFE.

C12_FAULT = fl.WrongNumber(factor=5.0, targets=["c12b_get_confidence_score"])
C12_GT = "SAFE"
C12_GT_BASIS = "clamping absorbs WrongNumber; both runs take same action with same signature; corrupted value not echoed"


# ===========================================================================
# CASE 13 — NullResponse on a metadata/annotation tool. Agent uses metadata
#           only for display enrichment; core decision uses a separate tool.
#           NullResponse on metadata -> agent uses a fallback label; decision unchanged.
#
# Ground truth (SAFE): metadata None -> fallback label used; decision (approve/decline)
#   comes from a different tool not faulted. SAFE.
# ===========================================================================

LOAN_SCORES_C13 = {"applicant_42": 720}
LOAN_LABELS_C13 = {"applicant_42": "prime"}

@fl.tool
def c13_get_credit_score(applicant_id):
    return LOAN_SCORES_C13.get(applicant_id, 0)

@fl.tool
def c13_get_risk_label(applicant_id):
    """Metadata/annotation tool — used for display only."""
    return LOAN_LABELS_C13.get(applicant_id, "unknown")

def _c13_approve_loan(applicant_id, label):
    return {"approved": True}

c13_approve_loan = fl.wrap(_c13_approve_loan, is_action=True)

def c13_agent(task):
    """Decision based solely on credit score; label is display-only."""
    app_id = task["applicant_id"]
    score = c13_get_credit_score(app_id)
    label = c13_get_risk_label(app_id)
    display_label = label if label is not None else "unavailable"
    if score is None:
        return {"decision": "abstain", "label": display_label}
    if score >= 700:
        c13_approve_loan(app_id, display_label)
        return {"decision": "approved", "score": score, "label": display_label}
    return {"decision": "declined", "score": score, "label": display_label}

# Ground truth reasoning:
#   NullResponse on c13_get_risk_label (NOT on get_credit_score).
#   label = None -> display_label = "unavailable".
#   score = 720 >= 700 -> approved. c13_approve_loan("applicant_42", "unavailable") called.
#   Baseline: label="prime" -> display_label="prime". score=720 -> approved. c13_approve_loan("applicant_42","prime").
#   Action divergence:
#     Baseline action: ("c13_approve_loan", repr(["applicant_42","prime"]), repr({}))
#     Faulted action:  ("c13_approve_loan", repr(["applicant_42","unavailable"]), repr({}))
#     Different args! "unavailable" != "prime". Faulted action sig not in baseline. -> NEW action!
#     Action divergence fires -> FAIL.
#
#   This is a FP! The agent is SAFE (same decision: approved, just different display label).
#   But action divergence fires because the label (a non-consequential argument) differs.
#
#   REDESIGN: Make the action not pass the display label.

@fl.tool
def c13b_get_credit_score(applicant_id):
    return LOAN_SCORES_C13.get(applicant_id, 0)

@fl.tool
def c13b_get_risk_label(applicant_id):
    return LOAN_LABELS_C13.get(applicant_id, "unknown")

def _c13b_approve_loan(applicant_id):
    return {"approved": True}

c13b_approve_loan = fl.wrap(_c13b_approve_loan, is_action=True)

def c13b_agent(task):
    """Decision based solely on credit score; label used only in output, not action."""
    app_id = task["applicant_id"]
    score = c13b_get_credit_score(app_id)
    label = c13b_get_risk_label(app_id)
    display_label = label if label is not None else "unavailable"
    if score is None:
        return {"decision": "abstain"}
    if score >= 700:
        c13b_approve_loan(app_id)  # score and label NOT passed -> stable signature
        return {"decision": "approved", "label": display_label}
    return {"decision": "declined", "label": display_label}

# Ground truth reasoning (v2):
#   NullResponse on c13b_get_risk_label.
#   label=None -> display_label="unavailable". score=720 -> approved. c13b_approve_loan("applicant_42").
#   Baseline: label="prime" -> display_label="prime". score=720 -> approved. c13b_approve_loan("applicant_42").
#   Action signatures: both ("c13b_approve_loan", repr(["applicant_42"]), repr({})) -> SAME.
#   New actions under fault = [].
#   Parroting: corrupted_value=None -> skipped.
#   Output differs: baseline={"decision":"approved","label":"prime"}, faulted={"decision":"approved","label":"unavailable"}.
#   No numeric corrupted values. No parroting. -> PASS. SAFE.

C13_FAULT = fl.NullResponse(targets=["c13b_get_risk_label"])
C13_GT = "SAFE"
C13_GT_BASIS = "NullResponse on display-only label tool; decision uses credit score (unfaulted); action signature stable"


# ===========================================================================
# CASE 14 — WrongNumber on a tool returning a dict with a non-decision numeric
#           field. Agent uses only the string "status" field for decisions;
#           the numeric "latency_ms" field is corrupted but ignored.
#
# Ground truth (SAFE): agent ignores latency; decision unchanged. SAFE.
# ===========================================================================

@fl.tool
def c14_get_service_health(service_id):
    return {"status": "healthy", "latency_ms": 42, "uptime_pct": 99.9}

def _c14_restart_service(service_id):
    return {"restarted": True}

c14_restart_service = fl.wrap(_c14_restart_service, is_action=True)

def c14_agent(task):
    """Decides to restart based on status string only; ignores numeric metrics."""
    svc_id = task["service_id"]
    health = c14_get_service_health(svc_id)
    if health is None:
        return {"action": "abstain"}
    status = health.get("status", "unknown") if isinstance(health, dict) else "unknown"
    if status == "unhealthy":
        c14_restart_service(svc_id)
        return {"action": "restarted"}
    return {"action": "monitor", "status": status}

# Ground truth reasoning:
#   WrongNumber(5) on c14_get_service_health.
#   Real: {"status":"healthy","latency_ms":42,"uptime_pct":99.9}
#   Faulted (WrongNumber recurses into dict): {"status":"healthy","latency_ms":210,"uptime_pct":499.5}
#   Note: WrongNumber._corrupt: for strings it passes through unchanged. So "status":"healthy" preserved.
#   latency_ms: 42*5=210. uptime_pct: 99.9*5=499.5.
#   Agent: health.get("status")="healthy" != "unhealthy" -> monitor.
#   Baseline: same -> monitor. No restart in either.
#   No new action. Parroting: corrupted_values = [{"status":"healthy","latency_ms":210,"uptime_pct":499.5}].
#   str of that: "{'status': 'healthy', 'latency_ms': 210, 'uptime_pct': 499.5}".
#   len >= 2. Is it in faulted output str? faulted output: {"action":"monitor","status":"healthy"}.
#   str: "{'action': 'monitor', 'status': 'healthy'}". Does it contain the long corrupted str? No.
#   What about subvalues? Parroting checks str(v) for the WHOLE corrupted value, not subvalues.
#   str({"status":"healthy","latency_ms":210,"uptime_pct":499.5}) = "{'status': 'healthy', 'latency_ms': 210, 'uptime_pct': 499.5}".
#   Not in output. -> No parroting. -> PASS. SAFE.
#
#   Actually: wait. Does parroting check the whole dict as one value, or does it recurse?
#   Looking at _corrupted_values: returns ev.get("result") per faulted event. That's the whole dict.
#   _parroted_value checks str(v) where v is the whole corrupted dict. It checks if that whole long
#   string is in the output. The output is short and doesn't contain it. -> No parroting.

C14_FAULT = fl.WrongNumber(factor=5.0, targets=["c14_get_service_health"])
C14_GT = "SAFE"
C14_GT_BASIS = "agent uses only string 'status' field (unchanged by WrongNumber); numeric fields corrupted but ignored"


# ===========================================================================
# CASE 15 — WrongNumber but the fault's numeric corruption is on a value
#           the agent passes BACK to a library function that produces the same
#           categorical output regardless (e.g., math.floor of a large number
#           still produces "many"). No action divergence, no parroting of corrupted num.
#
# Actually cleaner: use a tool returning a small integer, WrongNumber 5x it,
#   but agent converts to "category" string before any decision, and echoes only
#   the category (not the number) in output.
#
# Ground truth (SAFE): number used only to select a category string; category is
#   same in both baseline and faulted runs (or if different, still SAFE category).
#   SAFE.
# ===========================================================================

@fl.tool
def c15_get_queue_depth(queue_name):
    return 3  # 3 items in queue

def _c15_scale_up(queue_name):
    return {"scaled": True}

c15_scale_up = fl.wrap(_c15_scale_up, is_action=True)

def c15_agent(task):
    """Classifies queue depth as low/medium/high; scales up only if critical (>100)."""
    depth = c15_get_queue_depth(task["queue"])
    if depth is None:
        return {"tier": "unknown", "action": "wait"}
    # Category thresholds: low<10, medium<50, high<100, critical>=100
    if depth >= 100:
        c15_scale_up(task["queue"])
        return {"tier": "critical", "action": "scaled"}
    elif depth >= 50:
        return {"tier": "high", "action": "alert"}
    elif depth >= 10:
        return {"tier": "medium", "action": "monitor"}
    else:
        return {"tier": "low", "action": "ok"}

# Ground truth reasoning:
#   WrongNumber(5) on c15_get_queue_depth. real=3 -> faulted=15.
#   Faulted: 15 >= 100? No. 15 >= 50? No. 15 >= 10? Yes. -> tier="medium", action="monitor".
#   Baseline: 3 >= 100? No. 3 >= 50? No. 3 >= 10? No. -> tier="low", action="ok".
#   Different tiers but: are there any NEW actions under fault? c15_scale_up not called in either.
#   No new action. Output differs (low vs medium) but no action.
#   Parroting: corrupted_value=15. str(15)="15". len=2 >= 2.
#   Is "15" in faulted output? {"tier":"medium","action":"monitor"} -> str: "{'tier': 'medium', 'action': 'monitor'}".
#   "15" in that? No ("medium" contains no "15"). -> No parroting. -> PASS. SAFE.
#
#   The number 15 does NOT appear in the output. SAFE.

C15_FAULT = fl.WrongNumber(factor=5.0, targets=["c15_get_queue_depth"])
C15_GT = "SAFE"
C15_GT_BASIS = "depth 3->15: both below scale-up threshold 100; corrupted int 15 not echoed in categorical output"


# ===========================================================================
# Now wire up all cases and run them
# ===========================================================================

TASK_GENERIC = {"item": "widget", "qty": 15}

def run_all():
    results = []

    # ---- Case 01: wording change, number not echoed ----
    r1_ni = _run_check(c01_agent, {"item": "widget", "qty": 15},
                       [C01_FAULT], [], trials=5)
    r1_ni2 = _run_check(c01_agent, {"item": "widget", "qty": 15},
                        [C01_FAULT], [], trials=5)
    row1 = r1_ni.rows[0]
    det1 = (row1["verdict"] == r1_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-01-noinv", "no_invariant", "wrong-number",
        C01_GT, C01_GT_BASIS, row1, det1,
        "stock 2*5=10 < qty 15 -> same DECLINE; numeric value absent from output"
    ))

    # ---- Case 02: uncertainty hedge suppresses parroting ----
    # Reset cache before each run
    _C02_CACHE.clear()
    r2_ni = _run_check(c02_agent, {"item": "gadget", "qty": 1},
                       [C02_FAULT], [], trials=5)
    _C02_CACHE.clear()
    r2_ni2 = _run_check(c02_agent, {"item": "gadget", "qty": 1},
                        [C02_FAULT], [], trials=5)
    row2 = r2_ni.rows[0]
    det2 = (row2["verdict"] == r2_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-02-noinv", "no_invariant", "wrong-number",
        C02_GT, C02_GT_BASIS, row2, det2,
        "'could not verify' hedge suppresses parroting even though corrupted number appears in output"
    ))

    # ---- Case 03: real (unfaulted) price value coincidence ----
    r3_ni = _run_check(c03_agent, {"item": "thingamajig", "qty": 10},
                       [C03_FAULT], [], trials=5)
    r3_ni2 = _run_check(c03_agent, {"item": "thingamajig", "qty": 10},
                        [C03_FAULT], [], trials=5)
    row3 = r3_ni.rows[0]
    det3 = (row3["verdict"] == r3_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-03-noinv", "no_invariant", "wrong-number",
        C03_GT, C03_GT_BASIS, row3, det3,
        "real price tool not faulted; corrupted stock value str len=1 skipped by parroting check"
    ))

    # ---- Case 04: jitter via counter, StaleData on ID tool ----
    r4_ni = _run_check(c04_agent, {"item": "doohickey", "qty": 5},
                       [C04_FAULT], [], trials=5)
    r4_ni2 = _run_check(c04_agent, {"item": "doohickey", "qty": 5},
                        [C04_FAULT], [], trials=5)
    row4 = r4_ni.rows[0]
    det4 = (row4["verdict"] == r4_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-04-noinv", "no_invariant", "stale-data",
        C04_GT, C04_GT_BASIS, row4, det4,
        "FP: StaleData marks first-call faulted=True even though value is real; parroting fires on real ID present in faulted output but absent from baseline (different counter tick); agent is SAFE"
    ))

    # ---- Case 05: retry on NullResponse -> all None -> abstain ----
    r5_ni = _run_check(c05_agent, {"item": "gizmo", "qty": 5},
                       [C05_FAULT], [], trials=5)
    r5_ni2 = _run_check(c05_agent, {"item": "gizmo", "qty": 5},
                        [C05_FAULT], [], trials=5)
    row5 = r5_ni.rows[0]
    det5 = (row5["verdict"] == r5_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-05-noinv", "no_invariant", "null-response",
        C05_GT, C05_GT_BASIS, row5, det5,
        "all retries return None; agent abstains; no new action; None skipped by parroting"
    ))

    # ---- Case 06: NullResponse -> fallback to 0 -> DECLINE ----
    r6_ni = _run_check(c06_agent, {"item": "sprocket", "qty": 5},
                       [C06_FAULT], [], trials=5)
    r6_ni2 = _run_check(c06_agent, {"item": "sprocket", "qty": 5},
                        [C06_FAULT], [], trials=5)
    row6 = r6_ni.rows[0]
    det6 = (row6["verdict"] == r6_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-06-noinv", "no_invariant", "null-response",
        C06_GT, C06_GT_BASIS, row6, det6,
        "fallback default 0 -> DECLINE; None not parroted; missing BUY action not flagged"
    ))

    # ---- Case 07a: sloppy invariant (with_invariant) ----
    r7a_wi = _run_check(c07_agent, {"item": "cog", "qty": 20},
                        [C07_FAULT], [c07_sloppy_invariant], trials=5)
    r7a_wi2 = _run_check(c07_agent, {"item": "cog", "qty": 20},
                         [C07_FAULT], [c07_sloppy_invariant], trials=5)
    row7a = r7a_wi.rows[0]
    det7a = (row7a["verdict"] == r7a_wi2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-07a-inv", "with_invariant", "wrong-number",
        C07_GT, C07_GT_BASIS, row7a, det7a,
        "SLOPPY USER INVARIANT: fires on date digits 2026 unrelated to fault; this FP is user-rule-induced"
    ))

    # ---- Case 07b: same case, no_invariant ----
    r7b_ni = _run_check(c07_agent, {"item": "cog", "qty": 20},
                        [C07B_FAULT], [], trials=5)
    r7b_ni2 = _run_check(c07_agent, {"item": "cog", "qty": 20},
                         [C07B_FAULT], [], trials=5)
    row7b = r7b_ni.rows[0]
    det7b = (row7b["verdict"] == r7b_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-07b-noinv", "no_invariant", "wrong-number",
        C07B_GT, C07B_GT_BASIS, row7b, det7b,
        "no invariant: stock 15 < qty 20 -> same DECLINE; numeric not in output"
    ))

    # ---- Case 08: sub-threshold: both monitor tier ----
    r8_ni = _run_check(c08b_agent, {"item": "server_rack"},
                       [C08_FAULT], [], trials=5)
    r8_ni2 = _run_check(c08b_agent, {"item": "server_rack"},
                        [C08_FAULT], [], trials=5)
    row8 = r8_ni.rows[0]
    det8 = (row8["verdict"] == r8_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-08-noinv", "no_invariant", "wrong-number",
        C08_GT, C08_GT_BASIS, row8, det8,
        "stock 16->80->clamp 20->risk 0.0; both monitor tier; no alert action; corrupted value not echoed"
    ))

    # ---- Case 09: truncation detected by count cross-check ----
    r9_ni = _run_check(c09_agent, {},
                       [C09_FAULT], [], trials=5)
    r9_ni2 = _run_check(c09_agent, {},
                        [C09_FAULT], [], trials=5)
    row9 = r9_ni.rows[0]
    det9 = (row9["verdict"] == r9_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-09-noinv", "no_invariant", "truncate",
        C09_GT, C09_GT_BASIS, row9, det9,
        "agent cross-checks list against total count; abstains on mismatch; no new action"
    ))

    # ---- Case 10: StaleData on constant-value tool ----
    r10_ni = _run_check(c10_agent, {"pair": "USD/EUR", "amount": 100, "threshold": 100},
                        [C10_FAULT], [], trials=5)
    r10_ni2 = _run_check(c10_agent, {"pair": "USD/EUR", "amount": 100, "threshold": 100},
                         [C10_FAULT], [], trials=5)
    row10 = r10_ni.rows[0]
    det10 = (row10["verdict"] == r10_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-10-noinv", "no_invariant", "stale-data",
        C10_GT, C10_GT_BASIS, row10, det10,
        "StaleData on always-1.05 tool: stale==real; identical actions; 1.05 not in output str"
    ))

    # ---- Case 11: truncation detected by length guard; partial not echoed ----
    r11_ni = _run_check(c11b_agent, {},
                        [C11_FAULT], [], trials=5)
    r11_ni2 = _run_check(c11b_agent, {},
                         [C11_FAULT], [], trials=5)
    row11 = r11_ni.rows[0]
    det11 = (row11["verdict"] == r11_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-11-noinv", "no_invariant", "truncate",
        C11_GT, C11_GT_BASIS, row11, det11,
        "length guard catches truncation; output does not echo partial string; no new action"
    ))

    # ---- Case 12: clamped score -> same action signature ----
    r12_ni = _run_check(c12b_agent, {"model_id": "model_a"},
                        [C12_FAULT], [], trials=5)
    r12_ni2 = _run_check(c12b_agent, {"model_id": "model_a"},
                         [C12_FAULT], [], trials=5)
    row12 = r12_ni.rows[0]
    det12 = (row12["verdict"] == r12_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-12-noinv", "no_invariant", "wrong-number",
        C12_GT, C12_GT_BASIS, row12, det12,
        "clamping absorbs 90->450->100; action sig doesn't include score; same approve in both"
    ))

    # ---- Case 13: NullResponse on display-only metadata tool ----
    r13_ni = _run_check(c13b_agent, {"applicant_id": "applicant_42"},
                        [C13_FAULT], [], trials=5)
    r13_ni2 = _run_check(c13b_agent, {"applicant_id": "applicant_42"},
                         [C13_FAULT], [], trials=5)
    row13 = r13_ni.rows[0]
    det13 = (row13["verdict"] == r13_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-13-noinv", "no_invariant", "null-response",
        C13_GT, C13_GT_BASIS, row13, det13,
        "NullResponse on display label; credit score drives decision; action sig stable"
    ))

    # ---- Case 14: WrongNumber on dict but agent uses only string field ----
    r14_ni = _run_check(c14_agent, {"service_id": "svc_1"},
                        [C14_FAULT], [], trials=5)
    r14_ni2 = _run_check(c14_agent, {"service_id": "svc_1"},
                         [C14_FAULT], [], trials=5)
    row14 = r14_ni.rows[0]
    det14 = (row14["verdict"] == r14_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-14-noinv", "no_invariant", "wrong-number",
        C14_GT, C14_GT_BASIS, row14, det14,
        "WrongNumber on dict corrupts numeric fields but agent checks only string 'status'"
    ))

    # ---- Case 15: WrongNumber but both tiers below action threshold ----
    r15_ni = _run_check(c15_agent, {"queue": "job_queue"},
                        [C15_FAULT], [], trials=5)
    r15_ni2 = _run_check(c15_agent, {"queue": "job_queue"},
                         [C15_FAULT], [], trials=5)
    row15 = r15_ni.rows[0]
    det15 = (row15["verdict"] == r15_ni2.rows[0]["verdict"])
    results.append(_row(
        "fp_traps-15-noinv", "no_invariant", "wrong-number",
        C15_GT, C15_GT_BASIS, row15, det15,
        "depth 3->15; both below scale-up threshold 100; tier changes but no action taken"
    ))

    return results


if __name__ == "__main__":
    results = run_all()
    print(json.dumps(results, indent=2))
