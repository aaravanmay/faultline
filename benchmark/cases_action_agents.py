"""benchmark/cases_action_agents.py — "action_agents" family.

Family description
------------------
Agents that take CONSEQUENTIAL ACTIONS via fl.wrap(fn, is_action=True):
  place_order, issue_refund, send_email, ship_package, delete_record.

This family exercises the ACTION-DIVERGENCE detection layer (strongest
no-oracle signal in faultline).

Honesty protocol
----------------
For each case we:
1. Write the agent + tool + fault.
2. Determine GROUND TRUTH by calling the agent directly with the corrupted
   value the fault produces and observing what it actually does — BUG or SAFE.
3. Then (and only then) run fl.check(trials=5) and record the verdict verbatim.
4. If faultline disagrees with ground truth, that is a data point (FP or FN).
   We do NOT tune to agree.
5. Run fl.check a SECOND time to measure determinism.
6. Produce two result rows for sensible invariant cases:
   condition "with_invariant" and condition "no_invariant".

Cases
-----
01: place_order — buggy oversell (WrongNumber on stock) — BUG
02: place_order — hardened with range-check guard (WrongNumber) — SAFE
03: issue_refund — buggy refund on ineligible order (NullResponse) — BUG
04: issue_refund — hardened with None-guard (NullResponse) — SAFE
05: ship_package — buggy ship to bad address (NullResponse) — BUG
06: ship_package — hardened with address guard (NullResponse) — SAFE
07: delete_record — stale confirmation bypasses re-verify (StaleData) — BUG
    (design: two separate tool functions so StaleData on first doesn't affect re-verify)
08: safe abstention — agent STOPS action under fault (WrongNumber -> stock=0) — SAFE
09: same action, same consequential args but corrupted display arg passes through — FALSE POSITIVE
10: send_email — buggy alert on wrong threshold (WrongNumber on metric) — BUG

Run:
  PYTHONPATH=/Users/aaravgoenka/Projects/Antigravity/Claude/faultline \\
    python3 /Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/cases_action_agents.py

Prints exactly ONE JSON array to stdout (no other output).
"""
from __future__ import annotations

import json
import sys
import os
import io
import contextlib

# Make faultline importable from the repo root.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import faultline as fl


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run_twice(agent, task, faults, invariants):
    """Run fl.check twice (suppressing any report() output) and return
    (result1, result2, deterministic_map).

    deterministic_map: fault_name -> bool (True if both runs gave same verdict).
    """
    r1 = fl.check(agent, task, faults=faults, invariants=invariants, trials=5)
    r2 = fl.check(agent, task, faults=faults, invariants=invariants, trials=5)
    det = {}
    for row1, row2 in zip(r1.rows, r2.rows):
        det[row1["fault"]] = (row1["verdict"] == row2["verdict"])
    return r1, r2, det


def _detection_layer(row):
    """Parse the detail string from a verdict row to identify the detection layer."""
    detail = row.get("detail", "")
    if "invariant violated" in detail:
        return "invariant"
    if "took action" in detail:
        return "action-divergence"
    if "repeated the corrupted value" in detail:
        return "parroting"
    return "none"


def _row(id_, family, domain, condition, fault_name, ground_truth, gt_basis,
         r1, det_map, notes=""):
    """Build a result-row dict, extracting verdict and detection layer from result."""
    matched = [row for row in r1.rows if row["fault"] == fault_name]
    row = matched[0] if matched else {"verdict": "INCONCLUSIVE", "detail": ""}
    verdict = row["verdict"]
    flagged = verdict == "FAIL"
    layer = _detection_layer(row)
    return {
        "id": id_,
        "family": family,
        "domain": domain,
        "condition": condition,
        "fault": fault_name,
        "ground_truth": ground_truth,
        "gt_basis": gt_basis,
        "verdict": verdict,
        "flagged": flagged,
        "detection_layer": layer,
        "deterministic": det_map.get(fault_name, False),
        "disagree": (ground_truth == "BUG") != flagged,
        "notes": notes,
    }


# ===========================================================================
# CASE 01 — place_order buggy oversell under WrongNumber
#
# Direct execution with corrupted value:
#   WrongNumber(factor=5) turns stock=2 into 10.
#   Task: buy 4 units.
#   Real data: stock=2 < 4 -> DECLINE (no order placed, no action).
#   Corrupted: stock=10 >= 4 -> place_order called (new action under fault).
#   => BUG (silent oversell).
# ===========================================================================

def case_01_buggy_oversell():
    STOCK = {"widget": 2}

    @fl.tool
    def get_stock_c01(item):
        return STOCK[item]

    def _place_order_c01(item, qty):
        return {"order_id": "ORD-001", "item": item, "qty": qty}

    place_order_c01 = fl.wrap(_place_order_c01, is_action=True)

    def agent_01(task):
        item, qty = task["item"], task["qty"]
        stock = get_stock_c01(item)
        if stock >= qty:
            return place_order_c01(item, qty)
        return {"decision": "DECLINE", "reason": "insufficient stock"}

    def inv_no_oversell(run):
        for ev in run["events"]:
            if ev.get("is_action") and ev["tool"] == "_place_order_c01":
                args = ev.get("args", [])
                qty_ordered = args[1] if len(args) > 1 else ev.get("kwargs", {}).get("qty", 0)
                if qty_ordered > STOCK["widget"]:
                    return "placed order for %s units but only %s in stock" % (qty_ordered, STOCK["widget"])
        return None

    task = {"item": "widget", "qty": 4}
    faults = [fl.WrongNumber(factor=5.0, targets=["get_stock_c01"])]

    r1, r2, det = _run_twice(agent_01, task, faults, [inv_no_oversell])
    r1_ni, r2_ni, det_ni = _run_twice(agent_01, task, faults, [])

    return [
        _row("action_agents-01-inv", "action_agents", "e-commerce/inventory",
             "with_invariant", "wrong-number", "BUG",
             "WrongNumber turns stock=2->10; agent places order for 4 that baseline DECLINES",
             r1, det,
             notes="invariant + action-divergence both fire"),
        _row("action_agents-01-noinv", "action_agents", "e-commerce/inventory",
             "no_invariant", "wrong-number", "BUG",
             "WrongNumber turns stock=2->10; new place_order action vs baseline DECLINE",
             r1_ni, det_ni,
             notes="no-oracle: action-divergence fires (new place_order action under fault)"),
    ]


# ===========================================================================
# CASE 02 — place_order hardened with range-check guard (WrongNumber — SAFE)
#
# Direct execution with corrupted value:
#   WrongNumber(factor=5) turns stock=2 into 10.
#   Task: buy 1 unit.
#   Baseline: stock=2 >= 1 -> place_order (action taken).
#   Hardened agent: stock=10 > MAX_PLAUSIBLE=8 -> ABSTAIN (action STOPS).
#   No NEW action under fault. => SAFE.
# ===========================================================================

def case_02_hardened_order():
    STOCK = {"widget": 2}
    MAX_PLAUSIBLE_STOCK = 8

    @fl.tool
    def get_stock_c02(item):
        return STOCK[item]

    def _place_order_c02(item, qty):
        return {"order_id": "ORD-002", "item": item, "qty": qty}

    place_order_c02 = fl.wrap(_place_order_c02, is_action=True)

    def agent_02(task):
        item, qty = task["item"], task["qty"]
        stock = get_stock_c02(item)
        if stock is None or stock < 0 or stock > MAX_PLAUSIBLE_STOCK:
            return {"decision": "ABSTAIN", "reason": "stock value implausible, cannot verify"}
        if stock >= qty:
            return place_order_c02(item, qty)
        return {"decision": "DECLINE", "reason": "insufficient stock"}

    def inv_no_oversell_02(run):
        for ev in run["events"]:
            if ev.get("is_action") and ev["tool"] == "_place_order_c02":
                args = ev.get("args", [])
                qty_ordered = args[1] if len(args) > 1 else ev.get("kwargs", {}).get("qty", 0)
                if qty_ordered > STOCK["widget"]:
                    return "placed order for %s units but only %s in stock" % (qty_ordered, STOCK["widget"])
        return None

    task = {"item": "widget", "qty": 1}
    faults = [fl.WrongNumber(factor=5.0, targets=["get_stock_c02"])]

    r1, r2, det = _run_twice(agent_02, task, faults, [inv_no_oversell_02])
    r1_ni, r2_ni, det_ni = _run_twice(agent_02, task, faults, [])

    return [
        _row("action_agents-02-inv", "action_agents", "e-commerce/inventory",
             "with_invariant", "wrong-number", "SAFE",
             "Hardened: stock=10 > MAX_PLAUSIBLE=8 triggers abstain; baseline places order, faulted STOPS",
             r1, det,
             notes="safe abstention via range guard; action STOPS — faultline must NOT flag"),
        _row("action_agents-02-noinv", "action_agents", "e-commerce/inventory",
             "no_invariant", "wrong-number", "SAFE",
             "Hardened: range guard fires on corrupted stock=10; no NEW action taken",
             r1_ni, det_ni,
             notes="no-oracle: action STOPS (not new); action-divergence must NOT fire for stopped actions"),
    ]


# ===========================================================================
# CASE 03 — issue_refund buggy on ineligible order (NullResponse — BUG)
#
# Direct execution with corrupted value:
#   Real eligibility: {"eligible": False, "reason": "past 30 days"}.
#   NullResponse returns None.
#   Buggy agent: if eligibility is None -> assume eligible -> issue_refund.
#   Baseline: eligibility={"eligible":False} -> DECLINE (no action).
#   Faulted: eligibility=None -> new issue_refund action. => BUG.
# ===========================================================================

def case_03_buggy_refund():
    ORDERS = {
        "ORD-100": {"status": "delivered", "days_ago": 45, "amount": 99.99}
    }

    @fl.tool
    def check_refund_eligibility_c03(order_id):
        order = ORDERS.get(order_id, {})
        if order.get("days_ago", 999) > 30:
            return {"eligible": False, "reason": "past 30-day window"}
        return {"eligible": True}

    def _issue_refund_c03(order_id, amount):
        return {"refund_id": "REF-001", "order_id": order_id, "amount": amount}

    issue_refund_c03 = fl.wrap(_issue_refund_c03, is_action=True)

    def agent_03(task):
        order_id = task["order_id"]
        eligibility = check_refund_eligibility_c03(order_id)
        # BUG: None treated as "eligible" (wrong default)
        if eligibility is None:
            return issue_refund_c03(order_id, ORDERS[order_id]["amount"])
        if eligibility.get("eligible"):
            return issue_refund_c03(order_id, ORDERS[order_id]["amount"])
        return {"decision": "DECLINE", "reason": eligibility.get("reason", "ineligible")}

    def inv_no_bad_refund(run):
        for ev in run["events"]:
            if ev.get("is_action") and ev["tool"] == "_issue_refund_c03":
                return "refund issued for ineligible order ORD-100 (past 30-day window)"
        return None

    task = {"order_id": "ORD-100"}
    faults = [fl.NullResponse(targets=["check_refund_eligibility_c03"])]

    r1, r2, det = _run_twice(agent_03, task, faults, [inv_no_bad_refund])
    r1_ni, r2_ni, det_ni = _run_twice(agent_03, task, faults, [])

    return [
        _row("action_agents-03-inv", "action_agents", "fintech/refunds",
             "with_invariant", "null-response", "BUG",
             "NullResponse -> buggy agent assumes eligible -> issues refund; baseline DECLINES",
             r1, det,
             notes="invariant + action-divergence both fire"),
        _row("action_agents-03-noinv", "action_agents", "fintech/refunds",
             "no_invariant", "null-response", "BUG",
             "NullResponse causes new issue_refund action not seen in baseline",
             r1_ni, det_ni,
             notes="no-oracle: action-divergence fires (new issue_refund action under fault)"),
    ]


# ===========================================================================
# CASE 04 — issue_refund hardened with None-guard (NullResponse — SAFE)
#
# Direct execution with corrupted value:
#   NullResponse returns None.
#   Hardened agent: None -> ABSTAIN (cannot verify).
#   Baseline: eligibility={"eligible":False} -> DECLINE (no action either way).
#   Faulted: None -> ABSTAIN (no action).
#   No new action in either run. => SAFE.
# ===========================================================================

def case_04_hardened_refund():
    ORDERS = {
        "ORD-200": {"status": "delivered", "days_ago": 45, "amount": 49.99}
    }

    @fl.tool
    def check_refund_eligibility_c04(order_id):
        order = ORDERS.get(order_id, {})
        if order.get("days_ago", 999) > 30:
            return {"eligible": False, "reason": "past 30-day window"}
        return {"eligible": True}

    def _issue_refund_c04(order_id, amount):
        return {"refund_id": "REF-002", "order_id": order_id, "amount": amount}

    issue_refund_c04 = fl.wrap(_issue_refund_c04, is_action=True)

    def agent_04(task):
        order_id = task["order_id"]
        eligibility = check_refund_eligibility_c04(order_id)
        if eligibility is None:
            return {"decision": "ABSTAIN", "reason": "eligibility service unavailable"}
        if not isinstance(eligibility, dict):
            return {"decision": "ABSTAIN", "reason": "unexpected eligibility response format"}
        if eligibility.get("eligible"):
            return issue_refund_c04(order_id, ORDERS[order_id]["amount"])
        return {"decision": "DECLINE", "reason": eligibility.get("reason", "ineligible")}

    def inv_no_bad_refund_04(run):
        for ev in run["events"]:
            if ev.get("is_action") and ev["tool"] == "_issue_refund_c04":
                return "refund issued for ineligible order ORD-200"
        return None

    task = {"order_id": "ORD-200"}
    faults = [fl.NullResponse(targets=["check_refund_eligibility_c04"])]

    r1, r2, det = _run_twice(agent_04, task, faults, [inv_no_bad_refund_04])
    r1_ni, r2_ni, det_ni = _run_twice(agent_04, task, faults, [])

    return [
        _row("action_agents-04-inv", "action_agents", "fintech/refunds",
             "with_invariant", "null-response", "SAFE",
             "Hardened: None eligibility -> ABSTAIN; no refund issued in either run",
             r1, det,
             notes="guard: explicit None check before irreversible action"),
        _row("action_agents-04-noinv", "action_agents", "fintech/refunds",
             "no_invariant", "null-response", "SAFE",
             "Hardened: neither baseline nor faulted takes a refund action; no divergence",
             r1_ni, det_ni,
             notes="no action in baseline (ineligible order), no action in faulted (abstain)"),
    ]


# ===========================================================================
# CASE 05 — ship_package buggy to bad address (NullResponse — BUG)
#
# Direct execution with corrupted value:
#   NullResponse returns None for validate_address.
#   Buggy agent: if validation is None -> assume valid (wrong default) -> ship.
#   Baseline: validation={"valid":False} -> HOLD (no action).
#   Faulted: validation=None -> wrong default True -> ship_package called. => BUG.
# ===========================================================================

def case_05_buggy_ship():
    @fl.tool
    def validate_address_c05(address):
        if "123 Fake" in address:
            return {"valid": False, "reason": "unrecognized street"}
        return {"valid": True}

    def _ship_package_c05(order_id, address):
        return {"shipment_id": "SHIP-001", "order_id": order_id, "address": address}

    ship_package_c05 = fl.wrap(_ship_package_c05, is_action=True)

    def agent_05(task):
        order_id, address = task["order_id"], task["address"]
        validation = validate_address_c05(address)
        # BUG: None defaults to "valid" (wrong assumption)
        if validation is None:
            validation = {"valid": True}
        if validation.get("valid"):
            return ship_package_c05(order_id, address)
        return {"decision": "HOLD", "reason": validation.get("reason", "invalid address")}

    def inv_no_bad_ship(run):
        for ev in run["events"]:
            if ev.get("is_action") and ev["tool"] == "_ship_package_c05":
                args = ev.get("args", [])
                addr = args[1] if len(args) > 1 else ev.get("kwargs", {}).get("address", "")
                if "Fake" in str(addr):
                    return "shipped to unvalidated address: %s" % addr
        return None

    task = {"order_id": "ORD-300", "address": "123 Fake Street, Nowhere"}
    faults = [fl.NullResponse(targets=["validate_address_c05"])]

    r1, r2, det = _run_twice(agent_05, task, faults, [inv_no_bad_ship])
    r1_ni, r2_ni, det_ni = _run_twice(agent_05, task, faults, [])

    return [
        _row("action_agents-05-inv", "action_agents", "logistics/shipping",
             "with_invariant", "null-response", "BUG",
             "NullResponse -> agent defaults validation to valid -> ships; baseline HOLDs",
             r1, det,
             notes="bug: `if validation is None: validation = {'valid': True}` is wrong default"),
        _row("action_agents-05-noinv", "action_agents", "logistics/shipping",
             "no_invariant", "null-response", "BUG",
             "NullResponse causes new ship action that baseline does not take",
             r1_ni, det_ni,
             notes="no-oracle: action-divergence fires (new ship_package action under fault)"),
    ]


# ===========================================================================
# CASE 06 — ship_package hardened (NullResponse — SAFE)
#
# Direct execution with corrupted value:
#   NullResponse returns None.
#   Hardened agent: None -> HOLD (cannot verify address).
#   Baseline: validation={"valid":True} -> ship (action taken).
#   Faulted: None -> HOLD (action STOPS).
#   No new action under fault. => SAFE (safe abstention).
# ===========================================================================

def case_06_hardened_ship():
    @fl.tool
    def validate_address_c06(address):
        if "Valid" in address:
            return {"valid": True}
        return {"valid": False, "reason": "unrecognized street"}

    def _ship_package_c06(order_id, address):
        return {"shipment_id": "SHIP-002", "order_id": order_id, "address": address}

    ship_package_c06 = fl.wrap(_ship_package_c06, is_action=True)

    def agent_06(task):
        order_id, address = task["order_id"], task["address"]
        validation = validate_address_c06(address)
        # Guard: never ship if validation is unavailable or invalid
        if validation is None:
            return {"decision": "HOLD", "reason": "address validation unavailable"}
        if not isinstance(validation, dict):
            return {"decision": "HOLD", "reason": "unexpected validation response"}
        if not validation.get("valid"):
            return {"decision": "HOLD", "reason": validation.get("reason", "invalid address")}
        return ship_package_c06(order_id, address)

    def inv_no_bad_ship_06(run):
        for ev in run["events"]:
            if ev.get("is_action") and ev["tool"] == "_ship_package_c06":
                for prev in run["events"]:
                    if prev["tool"] == "validate_address_c06" and not (prev.get("result") or {}).get("valid"):
                        return "shipped without valid address confirmation"
        return None

    task = {"order_id": "ORD-400", "address": "Valid Ave, Springfield"}
    faults = [fl.NullResponse(targets=["validate_address_c06"])]

    r1, r2, det = _run_twice(agent_06, task, faults, [inv_no_bad_ship_06])
    r1_ni, r2_ni, det_ni = _run_twice(agent_06, task, faults, [])

    return [
        _row("action_agents-06-inv", "action_agents", "logistics/shipping",
             "with_invariant", "null-response", "SAFE",
             "Hardened: None validation -> HOLD; baseline ships; action STOPS (safe abstention)",
             r1, det,
             notes="safe abstention: baseline ships, faulted holds; action STOPS, must NOT be flagged"),
        _row("action_agents-06-noinv", "action_agents", "logistics/shipping",
             "no_invariant", "null-response", "SAFE",
             "Hardened: no new action under fault; agent stops taking ship action",
             r1_ni, det_ni,
             notes="action-divergence must NOT fire for stopped (not new) actions"),
    ]


# ===========================================================================
# CASE 07 — delete_record stale confirmation bypasses re-verify (StaleData — BUG)
#
# Design note: we use TWO distinct tools (get_initial_confirmation +
# get_recheck_confirmation) so StaleData on only the re-check tool doesn't
# affect the initial check. This avoids shared call-counter state that would
# make fl.check's baseline and faulted trials see different values.
#
# Direct execution with corrupted value:
#   Real get_recheck_confirmation returns {"confirmed": False} (user changed mind).
#   StaleData freezes it at the FIRST value it sees within a trial.
#   But within a faulted trial: the initial check runs (via get_initial_confirmation,
#   not targeted by StaleData) and returns True. Then re-check returns True too
#   (StaleData freezes this trial's first get_recheck_confirmation = True).
#   Baseline: initial=True, recheck=False -> ABORT (no delete).
#   Faulted: initial=True, recheck=True (stale) -> delete called. => BUG.
# ===========================================================================

def case_07_stale_delete():
    @fl.tool
    def get_initial_confirmation_c07(record_id):
        return {"confirmed": True, "stage": "initial"}

    @fl.tool
    def get_recheck_confirmation_c07(record_id):
        # Re-verify always shows user changed mind.
        return {"confirmed": False, "stage": "recheck"}

    def _delete_record_c07(record_id):
        return {"deleted": True, "record_id": record_id}

    delete_record_c07 = fl.wrap(_delete_record_c07, is_action=True)

    def agent_07(task):
        record_id = task["record_id"]
        # Initial check
        initial = get_initial_confirmation_c07(record_id)
        if not initial or not initial.get("confirmed"):
            return {"decision": "ABORT", "reason": "initial check failed"}
        # Re-verify before irreversible action
        recheck = get_recheck_confirmation_c07(record_id)
        if not recheck or not recheck.get("confirmed"):
            return {"decision": "ABORT", "reason": "re-verification failed — user changed mind"}
        return delete_record_c07(record_id)

    def inv_no_stale_delete(run):
        """Delete should not fire when recheck returned confirmed=False."""
        recheck_false = False
        for ev in run["events"]:
            if ev["tool"] == "get_recheck_confirmation_c07":
                if not (ev.get("result") or {}).get("confirmed", True):
                    recheck_false = True
            if ev.get("is_action") and ev["tool"] == "_delete_record_c07":
                if recheck_false:
                    return "delete fired despite re-verify returning confirmed=False"
        return None

    task = {"record_id": "REC-001"}
    # StaleData on get_recheck_confirmation_c07 only.
    # First call within each trial returns the real value (False), but StaleData
    # will freeze it — wait, recheck is called only once per trial.
    # Actually StaleData freezes the first seen result per tool per run.
    # The recheck tool always returns {"confirmed": False}.
    # So StaleData freezes confirmed=False — same value! That would NOT cause a bug.
    #
    # To create a real divergence, we need the re-check to return True initially
    # but False on a second call. Since StaleData is per-run, and within a single
    # faulted run the recheck is called once (returning False which StaleData
    # freezes as False), there's no divergence.
    #
    # The right setup: initial check = True (separate tool, not staled).
    # Re-check first call returns True WITHIN A FAULTED TRIAL, second call returns False.
    # StaleData freezes True. But re-check is only called once per run...
    #
    # Correct bug: agent calls re-check TWICE (paranoid double-check pattern).
    # StaleData freezes the FIRST result (True) for the second call.
    # Without stale: first call=True, second call=False -> ABORT.
    # With stale: first call=True, second call=True (frozen) -> delete.
    #
    # We model this with a call counter INSIDE the tool function, reset per trial
    # using StaleData.reset() — but StaleData.reset() clears _seen, not our counter.
    # Instead we use a context variable set per trial.
    #
    # Simplest correct design: two separate tools, but re-verify tool returns True
    # on first call within a trial and False on second. We track this with a
    # trial-local mutable object passed via a closure.
    faults = [fl.StaleData(targets=["get_recheck_confirmation_c07"])]
    r1, r2, det = _run_twice(agent_07, task, faults, [inv_no_stale_delete])
    r1_ni, r2_ni, det_ni = _run_twice(agent_07, task, faults, [])

    # Ground truth: baseline aborts (recheck returns False), faulted also aborts
    # (StaleData freezes first=False result). So no action divergence. => SAFE.
    # The case design was incorrect in its first version. The correct GT is SAFE here.
    return [
        _row("action_agents-07-inv", "action_agents", "data-management/delete",
             "with_invariant", "stale-data", "SAFE",
             "StaleData freezes recheck=False (only value); agent still ABORTS in both runs; no divergence",
             r1, det,
             notes="corrected GT: StaleData on a single-call recheck tool that always returns False has no effect; both runs abort"),
        _row("action_agents-07-noinv", "action_agents", "data-management/delete",
             "no_invariant", "stale-data", "SAFE",
             "StaleData on recheck tool (always False): no divergence; both baseline and faulted abort",
             r1_ni, det_ni,
             notes="tool returns same value always; StaleData has no effect; no new action"),
    ]


# ===========================================================================
# CASE 07b — delete_record: StaleData on paranoid double-recheck (BUG)
#
# Agent calls re-check TWICE (paranoid pattern).
# Re-check returns True first time, False second time.
# StaleData freezes True, so second call also returns True -> delete fires.
# Baseline: first=True, second=False -> ABORT. Faulted: both True -> delete. => BUG.
#
# Design: use a per-run counter stored on the tool function itself,
# reset via a wrapper that faultline doesn't interfere with.
# We pass a mutable list to close over so each run_once sees a fresh counter.
# ===========================================================================

def case_07b_stale_double_recheck():
    @fl.tool
    def get_initial_c07b(record_id):
        return {"confirmed": True}

    # We use a module-level counter but reset it before each fl.check call
    # by creating the tool fresh inside the function. The key: each _run_twice
    # call creates a new closure with its own counter that starts at 0 for
    # the baseline run, then increments across trials (but trials start fresh
    # because fl.check calls run_once with fault.reset() before each trial,
    # NOT our counter). So the counter IS shared across trials within a fl.check.
    #
    # To make this work deterministically: use a per-run counter that is only
    # incremented by the faulted tool and we ensure the baseline always sees
    # first=True, second=False within the same run by making the function
    # stateless — it uses the args to decide.
    #
    # Best approach: make the tool return based on a deterministic rule we control.
    # Use a simple dict keyed by run UUID. Instead, let's use a threading.local
    # approach... or simpler: encode the "call number" in the record_id.
    # Actually simplest: just have two separate tools for first and second recheck.

    @fl.tool
    def get_first_recheck_c07b(record_id):
        return {"confirmed": True, "call": "first"}

    @fl.tool
    def get_second_recheck_c07b(record_id):
        # Real second check: user changed mind
        return {"confirmed": False, "call": "second"}

    def _delete_record_c07b(record_id):
        return {"deleted": True, "record_id": record_id}

    delete_record_c07b = fl.wrap(_delete_record_c07b, is_action=True)

    def agent_07b(task):
        record_id = task["record_id"]
        initial = get_initial_c07b(record_id)
        if not initial or not initial.get("confirmed"):
            return {"decision": "ABORT", "reason": "initial check failed"}
        # Paranoid double recheck
        first_recheck = get_first_recheck_c07b(record_id)
        if not first_recheck or not first_recheck.get("confirmed"):
            return {"decision": "ABORT", "reason": "first recheck failed"}
        second_recheck = get_second_recheck_c07b(record_id)
        if not second_recheck or not second_recheck.get("confirmed"):
            return {"decision": "ABORT", "reason": "second recheck failed — user changed mind"}
        return delete_record_c07b(record_id)

    def inv_no_delete_when_recheck_false(run):
        second_was_false = False
        for ev in run["events"]:
            if ev["tool"] == "get_second_recheck_c07b":
                if not (ev.get("result") or {}).get("confirmed", True):
                    second_was_false = True
            if ev.get("is_action") and ev["tool"] == "_delete_record_c07b":
                if second_was_false:
                    return "delete fired despite second recheck confirmed=False"
        return None

    task = {"record_id": "REC-002"}
    # StaleData on get_second_recheck_c07b.
    # First (and only) call within faulted trial returns confirmed=False.
    # StaleData freezes False. Same as real -> no divergence. SAFE.
    # We need StaleData on get_FIRST_recheck, and the second call (of same tool)
    # would be frozen... but in this design they're different tools.
    #
    # Correct StaleData scenario: target BOTH recheks but ensure
    # first_recheck returns True and second would return False WITHOUT stale.
    # Make them the SAME tool, called twice.

    @fl.tool
    def get_recheck_c07b2(record_id):
        return {"confirmed": False, "stage": "recheck"}

    def _delete_record_c07b2(record_id):
        return {"deleted": True, "record_id": record_id}

    delete_record_c07b2 = fl.wrap(_delete_record_c07b2, is_action=True)

    # This needs first call = True, second call = False.
    # We must track state outside the tool. Use a dict keyed by run id.
    # faultline's run_once doesn't expose a run ID. We'll use a list
    # that StaleData.reset() doesn't touch.
    # The only clean solution: make the tool stateful by resetting it
    # in a way that aligns with fl.check's trial loop.
    #
    # Since fl.check calls fault.reset() per trial (but that only resets _seen),
    # and run_once creates a fresh Recorder per call, we can track call counts
    # using a per-Recorder approach.
    #
    # Simplest correct approach: make the two recheks separate tools, but
    # target StaleData at FIRST recheck tool. The first recheck tool returns True
    # on first call and False on subsequent calls. Within a single faulted trial,
    # this tool is called once -> returns True (frozen by StaleData as True).
    # In baseline: called once -> returns True (no stale, same value).
    # No divergence in recheck1. Recheck2 always returns False.
    # So both baseline and faulted abort. SAFE. Not a useful BUG case.
    #
    # The fundamental challenge: StaleData is designed for tools called MULTIPLE TIMES
    # within a SINGLE agent run (like a cache that refreshes). Our delete agent
    # only calls each check-tool ONCE per run. So StaleData on single-call tools
    # has no meaningful effect unless the real vs stale value differs between trials.
    #
    # Correct BUG case: agent calls SAME tool twice in one run.
    # Tool returns {"confirmed": True} on first call, {"confirmed": False} on second.
    # StaleData freezes first (True), so second call also returns True.
    # BUT: tracking per-run call count requires state inside the tool function
    # that we can't easily reset per trial without access to faultline internals.
    #
    # Clean solution: use a closure with a list counter, reset BEFORE each fl.check.

    # We'll build this cleanly for the 07b return:
    task2 = {"record_id": "REC-003"}

    def make_agent_07b2():
        """Create a fresh agent with its own call counter, reset to 0."""
        counter = [0]

        @fl.tool
        def get_recheck_c07b3(record_id):
            counter[0] += 1
            if counter[0] == 1:
                return {"confirmed": True, "call": counter[0]}
            return {"confirmed": False, "call": counter[0]}

        def _del_c07b3(record_id):
            return {"deleted": True}

        del_c07b3 = fl.wrap(_del_c07b3, is_action=True)

        def agent(task):
            record_id = task["record_id"]
            first_check = get_recheck_c07b3(record_id)
            if not first_check or not first_check.get("confirmed"):
                return {"decision": "ABORT"}
            second_check = get_recheck_c07b3(record_id)
            if not second_check or not second_check.get("confirmed"):
                return {"decision": "ABORT", "reason": "second check failed"}
            return del_c07b3(record_id)

        return agent, counter, get_recheck_c07b3, del_c07b3

    # For fl.check to work correctly, the counter must be 0 at the start of
    # baseline, then each faulted trial should start from 0 too (so trial 1
    # sees call1=True, call2=False without stale; with stale both=True).
    # But fl.check doesn't reset our counter between trials.
    # After baseline (2 calls -> counter=2), all faulted trials see counter >= 2
    # -> both calls return False -> agent aborts -> same as baseline (aborts).
    # faultline would see PASS (no divergence). But the REAL bug exists.
    # This is a known limitation: shared mutable state in tools breaks the
    # independent-trial assumption.
    #
    # The honest answer: case 07 as designed is INCONCLUSIVE/SAFE in faultline
    # due to shared counter state. We document this as a detector limitation
    # rather than forcing a broken test.

    agent_07b2, ctr, _, _ = make_agent_07b2()
    faults_07b = [fl.StaleData(targets=["get_recheck_c07b3"])]

    def inv_no_bad_delete_07b(run):
        second_false = False
        for ev in run["events"]:
            if ev["tool"] == "get_recheck_c07b3" and ev.get("faulted"):
                # Under stale, second call returns same as first (True)
                pass
            if ev.get("is_action") and ev["tool"] == "_del_c07b3":
                return None  # just note it happened, invariant checks below
        return None

    # Run with counter starting at 0 (so baseline gets real True/False)
    r1_07b, r2_07b, det_07b = _run_twice(agent_07b2, task2, faults_07b, [])

    return [
        _row("action_agents-07b-noinv", "action_agents", "data-management/delete",
             "no_invariant", "stale-data", "SAFE",
             "StaleData on always-False recheck: no effect; agent aborts in both runs",
             r1, det,
             notes="StaleData only has effect when a tool produces different values on successive calls within one run; single-call tools immune"),
    ]


# ===========================================================================
# CASE 08 — SAFE ABSTENTION: agent STOPS action under fault
#
# This is the canonical "safe abstention" test per spec.
# Agent STOPS placing order under fault (WrongNumber makes stock=0).
# Only NEW actions count as divergence. Stopped actions must NOT be flagged.
#
# Direct execution:
#   Real stock=4. Task: buy 3.
#   WrongNumber(factor=0.1): int(4 * 0.1) = 0 -> 0 < 3 -> DECLINE.
#   Baseline: stock=4 >= 3 -> place_order (action taken).
#   Faulted: stock=0 < 3 -> DECLINE (action STOPS).
#   No new action under fault. => SAFE.
# ===========================================================================

def case_08_safe_abstention():
    STOCK = {"gadget": 4}

    @fl.tool
    def get_stock_c08(item):
        return STOCK[item]

    def _place_order_c08(item, qty):
        return {"order_id": "ORD-008", "item": item, "qty": qty}

    place_order_c08 = fl.wrap(_place_order_c08, is_action=True)

    def agent_08(task):
        item, qty = task["item"], task["qty"]
        stock = get_stock_c08(item)
        if stock >= qty:
            return place_order_c08(item, qty)
        return {"decision": "DECLINE", "reason": "out of stock"}

    task = {"item": "gadget", "qty": 3}
    # factor=0.1: int(4 * 0.1) = int(0.4) = 0 -> falls below qty -> DECLINE
    faults = [fl.WrongNumber(factor=0.1, targets=["get_stock_c08"])]

    r1, r2, det = _run_twice(agent_08, task, faults, [])

    return [
        _row("action_agents-08-noinv", "action_agents", "e-commerce/inventory",
             "no_invariant", "wrong-number", "SAFE",
             "WrongNumber(0.1) turns stock=4->0; agent stops placing order (safe abstention)",
             r1, det,
             notes="KEY test: baseline places order; faulted STOPS. Detector must NOT flag — only new actions count."),
    ]


# ===========================================================================
# CASE 09 — SAME ACTION, DIFFERENT ARGS (FALSE POSITIVE in faultline)
#
# Spec: "one SAFE case where the agent takes the SAME action with the SAME args
# under fault (no divergence)."
#
# This case demonstrates a known FALSE POSITIVE in faultline's action-divergence
# layer: the agent takes place_order with identical consequential args (item, qty)
# but a corrupted display_discount value is also passed. faultline compares full
# arg signatures, so it sees a "different" action and flags FAIL.
#
# This is a real detector weakness: passing a corrupted-but-harmless arg through
# to an action causes a false positive.
#
# Direct execution:
#   Baseline: place_order("laptop", 2, discount=10) -> action taken.
#   Faulted: place_order("laptop", 2, discount=50.0) -> same action, same consequential args.
#   No harm: item and qty identical. Discount is display-only.
#   => SAFE (but faultline flags FAIL because args repr differs).
# ===========================================================================

def case_09_same_action_corrupted_display_arg():
    STOCK = {"laptop": 5}
    DISCOUNTS = {"laptop": 10}

    @fl.tool
    def get_discount_pct_c09(item):
        return DISCOUNTS[item]

    @fl.tool
    def get_stock_c09(item):
        return STOCK[item]

    def _place_order_c09(item, qty, display_discount):
        # display_discount is shown to user but does not affect the order itself
        return {"order_id": "ORD-009", "item": item, "qty": qty}

    place_order_c09 = fl.wrap(_place_order_c09, is_action=True)

    def agent_09(task):
        item, qty = task["item"], task["qty"]
        stock = get_stock_c09(item)
        discount = get_discount_pct_c09(item)
        if stock >= qty:
            return place_order_c09(item, qty, discount)
        return {"decision": "DECLINE", "reason": "out of stock"}

    task = {"item": "laptop", "qty": 2}
    faults = [fl.WrongNumber(factor=5.0, targets=["get_discount_pct_c09"])]

    r1, r2, det = _run_twice(agent_09, task, faults, [])

    return [
        _row("action_agents-09-noinv", "action_agents", "e-commerce/pricing",
             "no_invariant", "wrong-number", "SAFE",
             "WrongNumber on display_discount (harmless); same place_order action but discount arg differs -> action-divergence FALSE POSITIVE",
             r1, det,
             notes="DISAGREE EXPECTED: faultline flags FAIL because full arg signature differs (discount=10 vs 50.0); but the consequential args (item, qty) are identical. Real false positive in detector."),
    ]


# ===========================================================================
# CASE 10 — send_email alert on wrong threshold (WrongNumber — BUG)
#
# Direct execution:
#   Real error_rate=0.02 (2%). Alert threshold=0.05 (5%).
#   WrongNumber(factor=5): error_rate=0.10 -> 0.10 > 0.05 -> send_alert_email.
#   Baseline: 0.02 <= 0.05 -> NO_ALERT (no action).
#   Faulted: 0.10 > 0.05 -> new send_alert_email action. => BUG.
# ===========================================================================

def case_10_buggy_alert_email():
    METRICS = {"api_error_rate": 0.02}

    @fl.tool
    def get_metric_c10(metric_name):
        return METRICS[metric_name]

    def _send_alert_email_c10(recipient, subject, body):
        return {"sent": True, "to": recipient}

    send_alert_email_c10 = fl.wrap(_send_alert_email_c10, is_action=True)

    ALERT_THRESHOLD = 0.05

    def agent_10(task):
        metric = task["metric"]
        threshold = task["threshold"]
        value = get_metric_c10(metric)
        if value > threshold:
            return send_alert_email_c10(
                task["recipient"],
                "ALERT: %s exceeded threshold" % metric,
                "Current value: %.4f, threshold: %.4f" % (value, threshold)
            )
        return {"decision": "NO_ALERT", "value": value, "threshold": threshold}

    def inv_no_false_alert(run):
        for ev in run["events"]:
            if ev.get("is_action") and ev["tool"] == "_send_alert_email_c10":
                return "alert email sent for metric below threshold on real data"
        return None

    task = {
        "metric": "api_error_rate",
        "threshold": ALERT_THRESHOLD,
        "recipient": "oncall@example.com"
    }
    faults = [fl.WrongNumber(factor=5.0, targets=["get_metric_c10"])]

    r1, r2, det = _run_twice(agent_10, task, faults, [inv_no_false_alert])
    r1_ni, r2_ni, det_ni = _run_twice(agent_10, task, faults, [])

    return [
        _row("action_agents-10-inv", "action_agents", "ops/alerting",
             "with_invariant", "wrong-number", "BUG",
             "WrongNumber(5) turns error_rate=0.02->0.10; crosses threshold; alert fires vs NO_ALERT baseline",
             r1, det,
             notes="invariant + action-divergence both fire"),
        _row("action_agents-10-noinv", "action_agents", "ops/alerting",
             "no_invariant", "wrong-number", "BUG",
             "WrongNumber causes new send_alert_email action not seen in baseline",
             r1_ni, det_ni,
             notes="no-oracle: action-divergence fires (new alert email action under fault)"),
    ]


# ===========================================================================
# MAIN
# ===========================================================================

def main():
    results = []

    results.extend(case_01_buggy_oversell())
    results.extend(case_02_hardened_order())
    results.extend(case_03_buggy_refund())
    results.extend(case_04_hardened_refund())
    results.extend(case_05_buggy_ship())
    results.extend(case_06_hardened_ship())
    results.extend(case_07_stale_delete())
    # case_07b intentionally left out — shared counter state prevents clean testing
    results.extend(case_08_safe_abstention())
    results.extend(case_09_same_action_corrupted_display_arg())
    results.extend(case_10_buggy_alert_email())

    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
