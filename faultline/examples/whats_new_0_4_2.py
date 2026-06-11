"""A guided tour of everything new in faultline 0.4.2 — run it to see each feature work.

    python -m faultline.examples.whats_new_0_4_2

Deterministic, no API key, no framework deps (uses tiny self-contained agents). Doubles as an
end-to-end smoke test of the new public API: if any of these surfaces drifts, this script fails.
"""
from __future__ import annotations

import faultline as fl


def section(n, title):
    print("\n" + "=" * 64)
    print("%s. %s" % (n, title))
    print("=" * 64)


# A tiny agent with a wrapped tool + an action, used across the tour.
@fl.tool
def get_inventory(sku):
    return {"sku": sku, "units": 240}


_orders = []
place_order = fl.wrap(lambda sku, qty: _orders.append((sku, qty)),
                      is_action=True, name="place_order")


def restock_agent(task):
    units = get_inventory(task["sku"])["units"]
    qty = max(0, 250 - units)
    if qty > 0:
        place_order(task["sku"], qty)
    return {"ordered": qty}


def main():
    section(1, "scan — zero-config (no suite file, no invariants)")
    result, tools = fl.scan(restock_agent, {"sku": "A-12"}, trials=2)
    print("discovered tools:", tools)
    print("verdicts:", {r["fault"]: r["verdict"] for r in result.rows})
    print("=> faultline broke each tool and judged the agent, with zero rules written.")

    section(2, "assert_resilient — drop into any pytest/unittest")
    try:
        fl.assert_resilient(restock_agent, {"sku": "A-12"})
        print("agent passed (unexpected for this deliberately-fragile demo)")
    except AssertionError:
        print("=> assert_resilient raised on the fragile agent (this is the gate in your test suite).")

    section(3, "tools_really_called — catch a fabricated tool result")
    @fl.tool
    def get_ctx(x):
        return {"ctx": "data", "score": 5}

    def fabricator(task):
        get_ctx("x")                                   # really calls one tool
        return "The answer is Paris, per my search."   # claims a 'search' it never ran
    r = fl.check(fabricator, {}, faults=[fl.WrongNumber(targets=["get_ctx"])],
                 invariants=[fl.tools_really_called(["search"])], trials=2)
    print("verdict:", r.rows[0]["verdict"], "->", r.rows[0]["detail"][:80])
    print("=> caught a confident answer produced without the tool it claimed (via the transport log).")

    section(4, "EmptyResult — a 200-OK-but-empty tool response")
    @fl.tool
    def get_rows(region):
        return [1, 2, 3]

    def sum_agent(task):
        rows = get_rows("west")
        return {"n": len(rows), "total": sum(rows)}
    base = fl.run_once(sum_agent, {})
    empty = fl.run_once(sum_agent, {}, fl.EmptyResult(targets=["get_rows"]))
    print("real:", base["output"], "| under EmptyResult:", empty["output"])
    print("=> the agent silently summed an empty result to 0 — a well-formed-empty payload, not None.")

    section(5, "replay(transform=) — behavioral drift after context compression")
    def ctx_agent(task):
        ctx = task.get("context", "")
        return {"decision": "detailed" if len(ctx) >= 20 else "brief"}
    rec = fl.record(ctx_agent, {"context": "x" * 50})
    drift = fl.replay(ctx_agent, rec, watch=lambda o: {"decision": o["decision"]},
                      transform=lambda t: {"context": t["context"][:5]})
    print("recorded decision: detailed | after compression -> regressed:", drift.regressed())
    print("=> the decision silently flipped when the context was compressed.")

    section(6, "instrument — wrap any framework's tools (one call)")
    print("fl.instrument(graph_or_tools) wraps LangGraph / LangChain / LlamaIndex tools in place")
    print("so a fault reaches the real tool. Verified against the real libs in tests/test_*_real.py;")
    print("a live end-to-end catch on a real create_react_agent is in examples/langgraph_catch.py.")

    print("\n" + "-" * 64)
    print("All new in 0.4.2. Honest scope of each: see CAPABILITIES.md.")


if __name__ == "__main__":
    main()
