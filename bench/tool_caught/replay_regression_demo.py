"""faultline mode-4 (REPLAY) catching a silent regression after a 'model upgrade'. No LLM.

Record what a known-good agent does, then replay the SAME task on the updated agent. faultline
flags that a consequential decision silently flipped - the "it passed last month, the model got
bumped, now it quietly does the wrong thing" failure.
"""
import faultline as fl

ELIGIBLE = {"order_123": False}   # this order is NOT eligible for a refund


@fl.tool
def check_eligibility(order_id):
    return ELIGIBLE[order_id]


def refund_agent_v1(task):                       # known-good: declines ineligible refunds
    eligible = check_eligibility(task["order_id"])
    return {"decision": "REFUND" if eligible else "DECLINE"}


def refund_agent_v2(task):                       # after a 'model upgrade' / refactor — silent regression
    check_eligibility(task["order_id"])
    return {"decision": "REFUND"}                # now approves regardless (no error, looks fine)


task = {"order_id": "order_123"}
good_run = fl.record(refund_agent_v1, task)      # capture the trusted behavior
fl.replay(refund_agent_v2, good_run,
          watch=lambda o: {"decision": o["decision"]},
          label="refund agent: behavior after a model upgrade").report()
