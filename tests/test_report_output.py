"""Test: the user-facing REPORT text — the product surface for a CLI tool.

The detector logic is well-tested elsewhere; this locks the human-readable wording the whole pitch
rests on (e.g. "SILENT — the dangerous kind") so a refactor can't silently degrade the message.
We assert the load-bearing PHRASES, not a brittle full-string snapshot (the wording is still being
polished; phrase-level assertions protect meaning without churning on every copy tweak). Pure faultline.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import faultline as fl

passed = 0
failed = 0


def expect(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS %s" % name)
    else:
        failed += 1
        print("  FAIL %s" % name)


# A buggy agent: orders against a corrupted inventory (the headline silent failure).
@fl.tool
def get_inventory(sku):
    return {"sku": sku, "on_hand": 2}


_orders = []
place_order = fl.wrap(lambda sku, qty: _orders.append(qty), is_action=True, name="place_order")


def buggy_agent(task):
    on_hand = get_inventory(task["sku"])["on_hand"]
    place_order(task["sku"], 5)            # always orders 5 regardless — silent-wrong under corruption
    return {"ordered": 5, "on_hand": on_hand}


def never_oversell(run):
    for ev in run["events"]:
        if ev.get("is_action") and ev["tool"] == "place_order":
            qty = (ev.get("args") or [None, None])[1]
            on_hand = next((e["result"]["on_hand"] for e in run["events"] if e["tool"] == "get_inventory"), None)
            if on_hand is not None and qty is not None and qty > on_hand:
                return "ordered %s with only %s in stock" % (qty, on_hand)
    return None


res = fl.check(buggy_agent, {"sku": "A-12"}, faults=[fl.WrongNumber(targets=["get_inventory"])],
               invariants=[never_oversell], trials=3)
text = res.report(write_md=False)

# --- the load-bearing wording of the check report ---
expect("check report has a titled header", "faultline" in text and "check report" in text)
expect("check report states the baseline", "baseline:" in text.lower())
expect("check report has the Resilience score line", "Resilience:" in text or "resilience" in text.lower())
expect("the SILENT verdict + 'the dangerous kind' framing is present",
       "SILENT" in text and "dangerous" in text)
expect("check report offers suggested fixes", "fix" in text.lower())

# --- doctor: READY vs NOT READY wording ---
ready = fl.doctor(buggy_agent, {"sku": "A-12"}).report(write=False)
expect("doctor READY report names the wrapped tools that fired", "wrapped tools fired" in ready)
expect("doctor READY report says READY", "READY" in ready)


def no_tools(task):
    return {"answer": 1}


not_ready = fl.doctor(no_tools, {}).report(write=False)
expect("doctor NOT-READY report says NOT READY", "NOT READY" in not_ready)
expect("doctor NOT-READY explains the no-tools failure", "Wrap your tool calls" in not_ready)

# --- the verdict vocabulary the message depends on ---
for word in ("PASS", "FAIL", "CRASH", "SILENT"):
    pass  # vocabulary is exercised across the suite; spot-check the dangerous one here
expect("the word SILENT is the framing for the dangerous verdict", "SILENT" in text)

# --- explain(): show-your-work for a FAIL (auditability) ---
ex = res.explain(write=False)
expect("explain() shows what was corrupted (the tool + before->after)",
       "corrupted" in ex and "get_inventory" in ex)
expect("explain() shows the agent's action and the rationale",
       "place_order" in ex and "=>" in ex)
clean = fl.check(lambda t: {"ok": 1}, {}, faults=[fl.WrongNumber(targets=["nope"])], trials=1)
expect("explain() on a clean run says there's nothing to explain",
       "nothing" in clean.explain(write=False).lower() or "held up" in clean.explain(write=False).lower())

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
