"""The full faultline interrogation of a realistic support agent — run honestly, report honestly.

    ./.venv311/bin/python examples/support_agent_battery.py            # free: scripted stand-in model
    ./.venv311/bin/python examples/support_agent_battery.py --live     # REAL Claude Haiku (uses your key)

No bugs were planted in the agent (see support_agent.py). Whatever this prints is what a
normally-written agent really does when its tools feed it bad data — including anything it
handles WELL. The transcript is written to support_battery_transcript.txt for the recording.
"""
from __future__ import annotations

import io
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import faultline as fl
import support_agent as sa

LIVE = "--live" in sys.argv


class Tee(io.TextIOBase):
    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            st.write(s)
        return len(s)

    def flush(self):
        for st in self.streams:
            st.flush()


def main():
    agent = sa.make_agent(use_stub=not LIVE, verbose=False)
    mode = "REAL Claude Haiku (temperature=0)" if LIVE else "scripted stand-in (free dev mode)"
    findings = []          # (ticket, fault, verdict, meaning)

    print("=" * 74)
    print("faultline · full battery vs a realistic support agent")
    print("model: %s   |   no planted bugs, no edits" % mode)
    print("=" * 74)

    # ── 0. preflight ───────────────────────────────────────────────────────
    print("\n[0] DOCTOR — can faultline even test this agent?")
    rep = fl.doctor(agent, sa.TICKETS["broken_item"])
    rep.report()

    # ── 1. honest baseline: no faults, hard tickets ────────────────────────
    print("\n[1] SCENARIOS — honest tickets, every tool tells the truth")
    sc = fl.scenarios(agent,
                      [("broken item (refund $42 due)", sa.TICKETS["broken_item"]),
                       ("47-day-old order (must DECLINE)", sa.TICKETS["late_refund"]),
                       ("policy question", sa.TICKETS["policy_q"])],
                      [sa.refund_follows_policy])
    sc.report()
    baseline_clean = sc.safe()

    # ── 2. chaos: break the tools, one fault at a time ─────────────────────
    print("\n[2] CHAOS — now the tools lie. Same agent, same tickets.")

    print("\n  T1 'broken item' — corrupt the ORDER LOOKUP (a stale cache / bad join):")
    r1 = fl.check(agent, sa.TICKETS["broken_item"],
                  faults=[fl.WrongNumber(factor=5.0, targets=["get_order"]),
                          fl.Truncate(targets=["get_order"]),
                          fl.NullResponse(targets=["get_order"])],
                  invariants=[sa.refund_follows_policy], trials=2)
    r1.report(write_md=False)
    r1.explain()
    for row in r1.rows:
        findings.append(("broken-item", row["fault"], row["verdict"], row["detail"]))

    print("\n  T2 '47-day-old order' — under-read the delivery age (0.2x: 47 days -> ~9):")
    r2 = fl.check(agent, sa.TICKETS["late_refund"],
                  faults=[fl.WrongNumber(factor=0.2, targets=["get_order"])],
                  invariants=[sa.refund_follows_policy], trials=2)
    r2.report(write_md=False)
    r2.explain()
    for row in r2.rows:
        findings.append(("late-refund", row["fault"], row["verdict"], row["detail"]))

    print("\n  T3 'policy question' — the KB comes back EMPTY (rate-limit / no hits):")
    r3 = fl.check(agent, sa.TICKETS["policy_q"],
                  faults=[fl.EmptyResult(targets=["search_kb"]),
                          fl.NullResponse(targets=["search_kb"])],
                  invariants=[sa.grounded_policy_answer], trials=2)
    r3.report(write_md=False)
    r3.explain()
    for row in r3.rows:
        findings.append(("policy-q", row["fault"], row["verdict"], row["detail"]))

    # ── 3. fabrication: did it ever answer policy WITHOUT searching? ───────
    print("\n[3] FABRICATION CHECK — a policy answer must come from a real search_kb call")
    run = fl.run_once(agent, sa.TICKETS["policy_q"])
    fab = sa.really_searched(run)
    print("   " + (("CAUGHT: " + fab) if fab else
                   "clean — the agent really called search_kb before answering"))
    findings.append(("policy-q", "fabrication-check", "FAIL" if fab else "PASS", fab or "really searched"))

    # ── 4. mine: learn its good behavior, state the rules nobody wrote ─────
    print("\n[4] MINE — rules learned from the agent's own good runs")
    spec = fl.mine(agent, [sa.TICKETS["broken_item"], sa.TICKETS["late_refund"]])
    spec.report()

    # ── 5. replay: pin today's behavior for the next model/prompt change ───
    print("\n[5] REPLAY — pin the 47-day ticket; future upgrades get diffed against this")
    rec = fl.record(agent, sa.TICKETS["late_refund"])
    rr = fl.replay(agent, rec, invariants=None)
    rr.report()

    # ── 6. the fix: same model + two glue seatbelts, same faults ────────────
    print("\n[6] THE FIX — same model, two seatbelts added in the GLUE (not the prompt):")
    print("    a) refunds are cross-checked against the PAYMENT PROCESSOR before firing")
    print("    b) an empty KB becomes 'cannot confirm policy' instead of silence")
    hardened = sa.make_agent(use_stub=not LIVE, hardened=True, verbose=False)
    fix_findings = []
    h1 = fl.check(hardened, sa.TICKETS["broken_item"],
                  faults=[fl.WrongNumber(factor=5.0, targets=["get_order"])],
                  invariants=[sa.refund_follows_policy], trials=2)
    h1.report(write_md=False)
    fix_findings += [("broken-item", r["fault"], r["verdict"]) for r in h1.rows]
    h2 = fl.check(hardened, sa.TICKETS["late_refund"],
                  faults=[fl.WrongNumber(factor=0.2, targets=["get_order"])],
                  invariants=[sa.refund_follows_policy], trials=2)
    h2.report(write_md=False)
    fix_findings += [("late-refund", r["fault"], r["verdict"]) for r in h2.rows]
    h3 = fl.check(hardened, sa.TICKETS["policy_q"],
                  faults=[fl.EmptyResult(targets=["search_kb"])],
                  invariants=[sa.grounded_policy_answer], trials=2)
    h3.report(write_md=False)
    fix_findings += [("policy-q", r["fault"], r["verdict"]) for r in h3.rows]
    fixed_green = all(v == "PASS" for _t, _f, v in fix_findings)
    print("\n   => hardened agent under the same faults: %s"
          % ("ALL GREEN — every catch above is now a blocked/escalated action" if fixed_green
             else "NOT fully green yet: %s" % fix_findings))

    # ── the honest verdict ──────────────────────────────────────────────────
    print("\n" + "=" * 74)
    print("HONEST SUMMARY")
    print("=" * 74)
    print("baseline on truthful tools: %s" % ("clean — the agent itself is fine" if baseline_clean
                                              else "NOT CLEAN — the agent has a bug on honest data"))
    caught = [f for f in findings if f[2] == "FAIL"]
    crashed = [f for f in findings if f[2] == "CRASH"]
    handled = [f for f in findings if f[2] == "PASS"]
    other = [f for f in findings if f[2] not in ("FAIL", "CRASH", "PASS")]
    print("silent failures CAUGHT : %d" % len(caught))
    for t, fa, _v, d in caught:
        print("    [%s · %s] %s" % (t, fa, d[:96]))
    print("crashes (loud, real)   : %d" % len(crashed))
    for t, fa, _v, d in crashed:
        print("    [%s · %s] %s" % (t, fa, d[:96]))
    print("handled safely         : %d" % len(handled))
    for t, fa, _v, d in handled:
        print("    [%s · %s] %s" % (t, fa, d[:96]))
    if other:
        print("mixed/inconclusive     : %d" % len(other))
        for t, fa, v, d in other:
            print("    [%s · %s] %s — %s" % (t, fa, v, d[:88]))
    if LIVE:
        print("-" * 74)
        print("total API cost of this entire interrogation: $%.4f" % sa.cost_usd())
    print("=" * 74)
    return findings


if __name__ == "__main__":
    log = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "support_battery_transcript.txt"), "w")
    sys.stdout = Tee(sys.__stdout__, log)
    try:
        main()
    finally:
        sys.stdout = sys.__stdout__
        log.close()
