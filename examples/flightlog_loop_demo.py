"""faultline mode-4 (flightlog loop): a recorded run on DISK becomes a regression test.

Record a known-good agent run to a file (the 'production trace'). Later, after a model upgrade, load
that file and replay it against the new agent - faultline flags the silent behavior change. This is
the test<->prod loop: real runs become deterministic CI guards.
"""
import os
import tempfile
import faultline as fl
from faultline.replay import save_trace, load_trace

ELIGIBLE = {"order_123": False}   # NOT eligible for a refund

@fl.tool
def check_eligibility(order_id):
    return ELIGIBLE[order_id]

def refund_agent_v1(task):                  # known-good: declines ineligible refunds
    return {"decision": "REFUND" if check_eligibility(task["order_id"]) else "DECLINE"}

def refund_agent_v2(task):                  # after a 'model upgrade' — silent regression
    check_eligibility(task["order_id"])
    return {"decision": "REFUND"}

if __name__ == "__main__":
    task = {"order_id": "order_123"}
    path = os.path.join(tempfile.gettempdir(), "faultline_refund_trace.json")

    good = fl.record(refund_agent_v1, task)
    save_trace(good, path)
    print("recorded a known-good run to disk:", path)

    # ...weeks later, after a model upgrade, in CI...
    trace = load_trace(path)
    fl.replay(refund_agent_v2, trace,
              watch=lambda o: {"decision": o["decision"]},
              label="refund agent: replay a SAVED trace after a model upgrade").report()
