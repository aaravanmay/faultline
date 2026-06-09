"""Runtime guard (the seatbelt) — tests. Deterministic, no API, no network.

Covers:
  1. clean path        — no violation -> the REAL action FIRES (sentinel side effect happens)
  2. shadow mode       — a violating action still FIRES but is recorded + on_violation called
  3. enforce mode      — a violating action RAISES GuardBlocked, side effect does NOT happen
  4. selective block   — multiple rules / actions, only the offending one is blocked
  5. rule raises loud  — a rule that itself raises is surfaced, never a false "all clear"
  + decorator form, .report(), and that the guard composes with fl.wrap WITHOUT
    breaking test-time stubbing (a Recorder still stubs is_action under fl.check).

Side-effect safety: every "action" here mutates an in-memory dict — no real
irreversible side effects in a test.

Run:  python3 tests/test_guard.py   (expects all passed).
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faultline as fl

results = []


def check(name, cond):
    results.append((name, bool(cond)))
    print(("  ok  " if cond else "FAIL  ") + name)


# A fresh in-memory "ledger" per test stands in for a real side effect (an order
# placed, a refund issued). The wrapped action mutates it; we assert on it.
def _make_place_order(ledger):
    def _place_order(item, qty):
        ledger.append((item, qty))          # the irreversible side effect (faked)
        return {"placed": item, "qty": qty}
    return fl.wrap(_place_order, is_action=True, name="place_order")


# ---------------------------------------------------------------------------
# 1. Clean path — no violation -> the REAL action FIRES and returns its real value
# ---------------------------------------------------------------------------
def _t_clean():
    ledger = []
    place_order = _make_place_order(ledger)

    def never_block(action):
        return None                          # no rule ever fires

    with fl.guard([never_block], mode="enforce") as g:
        ret = place_order("widget", 3)

    return ledger, ret, g


_ledger, _ret, _g = _t_clean()
check("clean: real action fired (sentinel side effect happened)", _ledger == [("widget", 3)])
check("clean: real return value flows back", _ret == {"placed": "widget", "qty": 3})
check("clean: no violations recorded", _g.violations == [])
check("clean: action was counted as checked", _g.checked == 1)


# ---------------------------------------------------------------------------
# 2. Shadow mode — a violating action STILL fires, but is recorded + on_violation called
# ---------------------------------------------------------------------------
def _t_shadow():
    ledger = []
    place_order = _make_place_order(ledger)
    seen = []

    def no_big_order(action):
        if action["tool"] == "place_order" and action["args"][1] > 5:
            return "order qty %d exceeds the cap of 5" % action["args"][1]
        return None

    with fl.guard([no_big_order], mode="shadow", on_violation=seen.append) as g:
        ret = place_order("widget", 10)      # violates, but shadow => still fires

    return ledger, ret, g, seen


_ledger, _ret, _g, _seen = _t_shadow()
check("shadow: violating action STILL fired (side effect happened)", _ledger == [("widget", 10)])
check("shadow: real value still returned", _ret == {"placed": "widget", "qty": 10})
check("shadow: violation recorded in .violations", len(_g.violations) == 1)
check("shadow: recorded violation is not marked blocked", _g.violations[0].blocked is False)
check("shadow: on_violation callback was invoked", len(_seen) == 1 and _seen[0] is _g.violations[0])
check("shadow: violation carries the tool + message", _g.violations[0].tool == "place_order"
      and "cap of 5" in _g.violations[0].message)


# ---------------------------------------------------------------------------
# 3. Enforce mode — a violating action RAISES GuardBlocked, side effect does NOT happen
# ---------------------------------------------------------------------------
def _t_enforce():
    ledger = []
    place_order = _make_place_order(ledger)

    def no_big_order(action):
        if action["args"][1] > 5:
            return "order qty %d exceeds the cap" % action["args"][1]
        return None

    raised = None
    with fl.guard([no_big_order], mode="enforce") as g:
        try:
            place_order("widget", 10)
        except fl.GuardBlocked as exc:
            raised = exc

    return ledger, raised, g


_ledger, _raised, _g = _t_enforce()
check("enforce: GuardBlocked was raised", isinstance(_raised, fl.GuardBlocked))
check("enforce: side effect did NOT happen (ledger empty)", _ledger == [])
check("enforce: blocked violation recorded as blocked", len(_g.violations) == 1
      and _g.violations[0].blocked is True)
check("enforce: GuardBlocked carries the offending action",
      _raised is not None and _raised.action is not None
      and _raised.action["tool"] == "place_order")


# ---------------------------------------------------------------------------
# 4. Selective block — multiple rules, multiple actions; only the offender blocked
# ---------------------------------------------------------------------------
def _t_selective():
    ledger = []

    def _issue_refund(account, amount):
        ledger.append(("refund", account, amount))
        return {"refunded": amount}
    issue_refund = fl.wrap(_issue_refund, is_action=True, name="issue_refund")

    def _send_email(to, body):
        ledger.append(("email", to))
        return {"sent": to}
    send_email = fl.wrap(_send_email, is_action=True, name="send_email")

    def refund_cap(action):
        if action["tool"] == "issue_refund" and action["args"][1] > 1000:
            return "refund $%d over the $1000 ceiling" % action["args"][1]
        return None

    def email_domain(action):
        if action["tool"] == "send_email" and not action["args"][0].endswith("@ok.com"):
            return "email to a non-allowlisted domain"
        return None

    blocked_tools = []
    with fl.guard([refund_cap, email_domain], mode="enforce") as g:
        # action A: a small refund -> allowed, fires
        issue_refund("acct-1", 50)
        # action B: a huge refund -> blocked
        try:
            issue_refund("acct-2", 9999)
        except fl.GuardBlocked as exc:
            blocked_tools.append(exc.action["tool"])
        # action C: an allowlisted email -> allowed, fires
        send_email("ops@ok.com", "hi")

    return ledger, blocked_tools, g


_ledger, _blocked_tools, _g = _t_selective()
check("selective: the small refund fired", ("refund", "acct-1", 50) in _ledger)
check("selective: the allowlisted email fired", ("email", "ops@ok.com") in _ledger)
check("selective: the over-cap refund did NOT fire",
      not any(e[0] == "refund" and e[2] == 9999 for e in _ledger))
check("selective: only the offending action was blocked", _blocked_tools == ["issue_refund"])
check("selective: exactly one violation recorded", len(_g.violations) == 1)
check("selective: three actions reached the guard", _g.checked == 3)


# ---------------------------------------------------------------------------
# 5. A rule that itself RAISES is surfaced loudly — never a false "all clear"
# ---------------------------------------------------------------------------
def _t_rule_raises():
    ledger = []
    place_order = _make_place_order(ledger)

    def broken_rule(action):
        # a real-world bug: assumes a key that isn't there
        return "blocked" if action["args"][7] else None   # IndexError

    surfaced = None
    with fl.guard([broken_rule], mode="enforce"):
        try:
            place_order("widget", 3)
        except fl.GuardRuleError as exc:
            surfaced = exc

    return ledger, surfaced


_ledger, _surfaced = _t_rule_raises()
check("rule-raises: error surfaced (not swallowed into a false PASS)",
      isinstance(_surfaced, fl.GuardRuleError))
check("rule-raises: the underlying cause is preserved",
      _surfaced is not None and isinstance(_surfaced.cause, IndexError))
check("rule-raises: action did NOT silently fire while the rule was broken",
      _ledger == [])


# ---------------------------------------------------------------------------
# Extra: decorator form works the same as the context-manager form
# ---------------------------------------------------------------------------
def _t_decorator():
    ledger = []
    place_order = _make_place_order(ledger)

    def no_big_order(action):
        if action["args"][1] > 5:
            return "too big"
        return None

    @fl.guard([no_big_order], mode="enforce")
    def run(qty):
        return place_order("widget", qty)

    ok = run(3)                              # under the cap -> fires
    blocked = False
    try:
        run(99)                              # over the cap -> blocked
    except fl.GuardBlocked:
        blocked = True
    return ledger, ok, blocked


_ledger, _ok, _blocked = _t_decorator()
check("decorator: allowed call fired", _ledger == [("widget", 3)] and _ok["qty"] == 3)
check("decorator: blocked call raised GuardBlocked", _blocked is True)


# ---------------------------------------------------------------------------
# Extra: .report() summarizes mode + violations
# ---------------------------------------------------------------------------
def _t_report():
    ledger = []
    place_order = _make_place_order(ledger)

    def no_big_order(action):
        if action["args"][1] > 5:
            return "exceeds cap"
        return None

    with fl.guard([no_big_order], mode="shadow") as g:
        place_order("widget", 9)
    return g.report(print_it=False)


_txt = _t_report()
check("report: mentions shadow mode", "mode: shadow" in _txt)
check("report: shows the violation", "exceeds cap" in _txt and "ALLOWED" in _txt)


# ---------------------------------------------------------------------------
# Composition: the guard does NOT break test-time stubbing. Under fl.check, an
# is_action tool is still stubbed (no real side effect) even though guard exists.
# ---------------------------------------------------------------------------
def _t_compose_with_check():
    ledger = []
    place_order = _make_place_order(ledger)

    @fl.tool
    def get_stock(item):
        return 2

    def agent(task):
        stock = get_stock(task["item"])
        if stock >= task["qty"]:
            place_order(task["item"], task["qty"])
            return {"decision": "BUY"}
        return {"decision": "DECLINE"}

    def must_not_oversell(run):
        out = run["output"]
        if out and out.get("decision") == "BUY":
            return "ordered out-of-stock goods"

    res = fl.check(agent, {"item": "widget", "qty": 3},
                   faults=[fl.WrongNumber(targets=["get_stock"])],
                   invariants=[must_not_oversell], trials=3)
    return ledger, res


_ledger, _res = _t_compose_with_check()
check("compose: fl.check did NOT fire the real action (test stubbing intact)", _ledger == [])
check("compose: fl.check still caught the silent oversell", _res.rows[0]["verdict"] == "FAIL")


# ---------------------------------------------------------------------------
# Extra: a plain (non-action) tool is untouched by the guard — only actions are governed
# ---------------------------------------------------------------------------
def _t_plain_tool_passthrough():
    @fl.tool
    def lookup(x):
        return x * 2

    def block_everything(action):
        return "nope"          # would block any ACTION, but lookup is not an action

    with fl.guard([block_everything], mode="enforce") as g:
        out = lookup(21)
    return out, g


_out, _g = _t_plain_tool_passthrough()
check("plain tool runs unblocked under a guard", _out == 42)
check("plain tool did not reach the guard (no action checked)", _g.checked == 0)


passed = sum(1 for _, c in results if c)
print("\n%d passed, %d failed" % (passed, len(results) - passed))
sys.exit(0 if passed == len(results) else 1)
