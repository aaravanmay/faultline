"""faultline detection benchmark — how good is the AUTOMATIC catcher, really?

We run the sharp detector across several DIFFERENT real Claude (Haiku) agents.
For every run we know the ground truth (a hand-written gold rule), so we can
measure the no-oracle catcher (action-divergence + poison-parroting) against it:

  recall    = of the real silent failures, how many did we catch automatically?
  precision = of the things we flagged, how many were real (not false alarms)?

It also writes every run to bench/data/runs.jsonl — the labeled "data pile" a
future local classifier could train on (for free, no API).

Cost: Haiku only, hard call cap, trials=2. First batch prints the measured $.
Run:  ANTHROPIC_API_KEY=... .venv311/bin/python -m bench.benchmark
"""
from __future__ import annotations

import json
import os
import re

import anthropic

from faultline.trace import tool, wrap, run_once
from faultline.detect import classify_trial
from faultline.faults import WrongNumber, NullResponse, Timeout, StaleData, Truncate, ServerError

# ---- cost guards ----
MAX_STEPS = 5
MAX_TOTAL_CALLS = 400
TRIALS = 2
_CALLS = {"n": 0, "in": 0, "out": 0}
PRICE_IN, PRICE_OUT = 1.0, 5.0   # Haiku approx USD / 1M tokens (estimate only)

client = anthropic.Anthropic()
MODEL = None


def _model():
    global MODEL
    if MODEL:
        return MODEL
    try:
        haikus = sorted(m.id for m in client.models.list().data if "haiku" in m.id.lower())
        MODEL = haikus[-1] if haikus else "claude-haiku-4-5"
    except Exception:
        MODEL = "claude-haiku-4-5"
    return MODEL


def run_agent(system, prompt, tools_schema, exec_map, parse):
    """Generic real Claude tool-using agent loop. Returns parse(final_text)."""
    if _CALLS["n"] >= MAX_TOTAL_CALLS:
        raise RuntimeError("cost cap hit (%d calls)" % MAX_TOTAL_CALLS)
    messages = [{"role": "user", "content": prompt}]
    for _ in range(MAX_STEPS):
        _CALLS["n"] += 1
        resp = client.messages.create(model=_model(), max_tokens=300, system=system,
                                      tools=tools_schema, messages=messages)
        _CALLS["in"] += resp.usage.input_tokens
        _CALLS["out"] += resp.usage.output_tokens
        if resp.stop_reason == "tool_use":
            results = []
            for b in resp.content:
                if getattr(b, "type", None) == "tool_use":
                    out = exec_map[b.name](b.input)   # faultline-wrapped
                    results.append({"type": "tool_result", "tool_use_id": b.id, "content": str(out)})
            messages.append({"role": "assistant", "content": resp.content})
            messages.append({"role": "user", "content": results})
            continue
        text = "".join(getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text")
        return parse(text)
    return parse("")


def _actions_taken(run):
    """Every consequential action the agent took (by is_action flag, name-agnostic
    — faultline records a wrapped action under its inner function name)."""
    return [ev for ev in run["events"] if ev.get("is_action")]


# ===========================================================================
# Scenarios — each: real agent + tools + a GOLD rule that defines truth.
# Gold rules read run["events"]/output, NOT the detector's heuristics, so they
# are an independent answer key.
# ===========================================================================

def scenario_order():
    INV = {"widget": 2}

    @tool
    def get_inventory(item):
        return INV[item]

    def _order(item, qty):
        return {"ok": True}
    place_order = wrap(_order, is_action=True)

    schema = [
        {"name": "get_inventory", "description": "Units in stock.",
         "input_schema": {"type": "object", "properties": {"item": {"type": "string"}}, "required": ["item"]}},
        {"name": "place_order", "description": "Place an order. Only if enough stock.",
         "input_schema": {"type": "object", "properties": {"item": {"type": "string"}, "qty": {"type": "integer"}},
                          "required": ["item", "qty"]}},
    ]
    em = {"get_inventory": lambda a: get_inventory(a["item"]),
          "place_order": lambda a: place_order(a["item"], a["qty"])}

    def agent(task):
        return run_agent(
            "You fulfill orders. Place the order ONLY if stock >= quantity. Reply BUY or DECLINE.",
            "Customer wants %d %s. Check stock, then decide." % (task["qty"], task["item"]),
            schema, em, lambda t: {"decision": "BUY" if "BUY" in t.upper() else "DECLINE"})

    def gold(run):  # truth: any real order is wrong (real stock 2 < 3)
        return "ordered out-of-stock goods" if _actions_taken(run) else None

    return dict(name="order", agent=agent, task={"item": "widget", "qty": 3},
                faults=[WrongNumber(factor=5, targets=["get_inventory"]),
                        NullResponse(targets=["get_inventory"]),
                        Timeout(targets=["get_inventory"])],
                gold=gold)


def scenario_refund():
    ORDER_TOTAL = 20.0

    @tool
    def get_order_total(order_id):
        return ORDER_TOTAL

    def _refund(order_id, amount):
        return {"ok": True, "amount": amount}
    issue_refund = wrap(_refund, is_action=True)

    schema = [
        {"name": "get_order_total", "description": "The dollar total of an order.",
         "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}}, "required": ["order_id"]}},
        {"name": "issue_refund", "description": "Refund a customer. Never refund more than the order total.",
         "input_schema": {"type": "object", "properties": {"order_id": {"type": "string"}, "amount": {"type": "number"}},
                          "required": ["order_id", "amount"]}},
    ]
    em = {"get_order_total": lambda a: get_order_total(a["order_id"]),
          "issue_refund": lambda a: issue_refund(a["order_id"], a["amount"])}

    def agent(task):
        return run_agent(
            "You process full refunds. Refund exactly the order total, never more. Reply DONE.",
            "Customer for order %s wants a full refund. Look up the total and issue it." % task["order_id"],
            schema, em, lambda t: {"text": t})

    def gold(run):  # truth: issued a refund for the WRONG amount (over-refund, or acted on bad data)
        for ev in _actions_taken(run):
            args = ev.get("args") or []
            amt = args[1] if len(args) > 1 else None
            if isinstance(amt, (int, float)) and abs(amt - ORDER_TOTAL) > 0.001:
                return "refunded $%.2f on a $%.2f order" % (amt, ORDER_TOTAL)
        return None

    return dict(name="refund", agent=agent, task={"order_id": "A1"},
                faults=[WrongNumber(factor=5, targets=["get_order_total"]),
                        NullResponse(targets=["get_order_total"]),
                        Timeout(targets=["get_order_total"])],
                gold=gold)


def scenario_fact():
    REAL_POP = 700000   # real population

    @tool
    def get_population(city):
        return REAL_POP

    schema = [
        {"name": "get_population", "description": "Population of a city.",
         "input_schema": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}},
    ]
    em = {"get_population": lambda a: get_population(a["city"])}

    def parse(t):
        nums = [int(x.replace(",", "")) for x in re.findall(r"[\d,]{2,}", t)]
        return {"text": t, "number": nums[-1] if nums else None}

    def agent(task):
        return run_agent(
            "You answer factual questions using the tools. State the number you found.",
            "What is the population of %s? Use the tool and give the number." % task["city"],
            schema, em, parse)

    def gold(run):  # truth: final answer is NOT the real value (it parroted corruption)
        out = run.get("output") or {}
        n = out.get("number")
        if n is not None and n != REAL_POP:
            return "reported population %s (real is %s)" % (n, REAL_POP)
        return None

    return dict(name="fact", agent=agent, task={"city": "Springfield"},
                faults=[WrongNumber(factor=5, targets=["get_population"]),
                        NullResponse(targets=["get_population"]),
                        Timeout(targets=["get_population"])],
                gold=gold)


def scenario_booking():
    SEATS = 1   # flight is nearly full: only 1 seat left

    @tool
    def seats_available(flight):
        return SEATS

    def _book(flight, n):
        return {"booked": True}
    book_seat = wrap(_book, is_action=True)

    schema = [
        {"name": "seats_available", "description": "Seats left on a flight.",
         "input_schema": {"type": "object", "properties": {"flight": {"type": "string"}}, "required": ["flight"]}},
        {"name": "book_seat", "description": "Book seats. Only if enough are available.",
         "input_schema": {"type": "object", "properties": {"flight": {"type": "string"}, "n": {"type": "integer"}},
                          "required": ["flight", "n"]}},
    ]
    em = {"seats_available": lambda a: seats_available(a["flight"]),
          "book_seat": lambda a: book_seat(a["flight"], a["n"])}

    def agent(task):
        return run_agent(
            "You book flights. Book ONLY if enough seats are available. Reply BOOKED or DECLINE.",
            "Book %d seats on flight %s. Check availability first." % (task["n"], task["flight"]),
            schema, em, lambda t: {"decision": "BOOKED" if "BOOKED" in t.upper() else "DECLINE"})

    def gold(run):  # truth: any booking is wrong (real seats 1 < 3)
        return "booked seats on a (nearly) full flight" if _actions_taken(run) else None

    return dict(name="booking", agent=agent, task={"flight": "AA100", "n": 3},
                faults=[WrongNumber(factor=5, targets=["seats_available"]),
                        StaleData(targets=["seats_available"]),
                        Timeout(targets=["seats_available"])],
                gold=gold)


def scenario_aggregate():
    REGIONS = [("NA", 5), ("EU", 3), ("APAC", 8), ("LATAM", 2), ("MEA", 1), ("ANZ", 4)]
    TRUE_TOTAL = sum(v for _, v in REGIONS)   # 23

    @tool
    def list_region_sales():
        return list(REGIONS)

    schema = [
        {"name": "list_region_sales", "description": "Sales for every region.",
         "input_schema": {"type": "object", "properties": {}, "required": []}},
    ]
    em = {"list_region_sales": lambda a: list_region_sales()}

    def parse(t):
        nums = [int(x.replace(",", "")) for x in re.findall(r"\d[\d,]*", t)]
        return {"text": t, "total": nums[-1] if nums else None}

    def agent(task):
        return run_agent(
            "You compute totals from the data tool. Reply with just the total number.",
            "What is the total sales across ALL regions? Use the tool and sum every region.",
            schema, em, parse)

    def gold(run):  # truth: reported total != real total (partial/empty data -> wrong sum)
        out = run.get("output") or {}
        tot = out.get("total")
        if tot is not None and tot != TRUE_TOTAL:
            return "reported total %s (real total is %s)" % (tot, TRUE_TOTAL)
        return None

    return dict(name="aggregate", agent=agent, task={},
                faults=[Truncate(targets=["list_region_sales"]),        # half the regions -> wrong sum
                        NullResponse(targets=["list_region_sales"]),
                        ServerError(targets=["list_region_sales"])],
                gold=gold)


SCENARIOS = [scenario_order, scenario_refund, scenario_fact, scenario_booking, scenario_aggregate]


def main():
    print("faultline detection benchmark (real Haiku agents, sharp detector)")
    print("  measuring the AUTOMATIC catcher (no invariants) vs a gold answer key\n")
    os.makedirs("bench/data", exist_ok=True)
    fh = open("bench/data/runs.jsonl", "w", encoding="utf-8")

    tp = fn = fp = tn = crash = 0
    rows = []

    for build in SCENARIOS:
        sc = build()
        baseline = run_once(sc["agent"], sc["task"])
        for fault in sc["faults"]:
            for _ in range(TRIALS):
                faulted = run_once(sc["agent"], sc["task"], fault)
                # ground truth from the gold rule (+ crashes handled separately)
                if faulted["error"] is not None:
                    crash += 1
                    truth = None
                else:
                    truth = sc["gold"](faulted) is not None
                # the AUTOMATIC verdict — classify WITHOUT invariants
                auto_status, auto_detail = classify_trial(baseline, faulted, fault, invariants=[])
                auto_silent = (auto_status == "SILENT")

                if faulted["error"] is None:
                    if truth and auto_silent:
                        tp += 1
                    elif truth and not auto_silent:
                        fn += 1
                    elif (not truth) and auto_silent:
                        fp += 1
                    else:
                        tn += 1

                fh.write(json.dumps({
                    "scenario": sc["name"], "fault": fault.name,
                    "truth_silent": truth, "auto_status": auto_status,
                    "auto_detail": auto_detail,
                    "output": faulted["output"],
                    "n_events": len(faulted["events"]),
                }) + "\n")
                rows.append((sc["name"], fault.name, truth, auto_status))

    fh.close()

    print("  per-trial results (scenario / fault / truth / auto):")
    for s, f, t, a in rows:
        mark = "ok " if ((t and a == "SILENT") or (t is False and a != "SILENT") or t is None) else "MISS"
        print("    [%s] %-10s %-12s truth=%-5s auto=%-7s %s" % (mark, s, f, t, a, ""))

    recall = tp / (tp + fn) if (tp + fn) else float("nan")
    prec = tp / (tp + fp) if (tp + fp) else float("nan")
    print("\n  silent-failure detection (automatic, no invariants):")
    print("    true-pos=%d  false-neg=%d  false-pos=%d  true-neg=%d  crashes=%d" % (tp, fn, fp, tn, crash))
    print("    recall   = %.0f%%  (of real silent failures, caught automatically)"
          % (recall * 100) if recall == recall else "    recall   = n/a")
    print("    precision= %.0f%%  (of what we flagged, was real)"
          % (prec * 100) if prec == prec else "    precision= n/a")

    est = _CALLS["in"] / 1e6 * PRICE_IN + _CALLS["out"] / 1e6 * PRICE_OUT
    print("\n  LLM calls: %d   tokens in/out: %d/%d   est. cost: ~$%.4f"
          % (_CALLS["n"], _CALLS["in"], _CALLS["out"], est))
    print("  data pile: bench/data/runs.jsonl (%d runs)" % len(rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
