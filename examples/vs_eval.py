"""faultline vs a plain eval — SAME agent, the eval passes, faultline catches the silent failure.

This is the whole thesis, made runnable. Your eval checks the agent's output on CLEAN data and goes
green. faultline breaks a tool and catches the agent confidently doing the wrong thing — the
200-OK-but-wrong your eval structurally never tests. Watch the eval pass, then watch faultline catch it.

    python3 examples/vs_eval.py        # no API key, ~1 second
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import faultline as fl

_KB = {"refund window": "Our refund window is 30 days from purchase."}


@fl.tool
def retrieve(query):
    """The retrieval tool. faultline will break this; the eval never touches it."""
    return [doc for key, doc in _KB.items() if key in query.lower()]


def generate(query, docs):
    # A real-looking generator: answers from sources, but FABRICATES from priors when there are none.
    if docs:
        return "Per our docs: " + " ".join(docs)
    return "Per our docs, the refund window is 14 days."        # confident, sourced-sounding, wrong


def agent(task):
    return {"answer": generate(task["query"], retrieve(task["query"]))}


TASK = {"query": "what is the refund window?"}


def run_plain_eval():
    """What a normal eval does: run the agent on clean data, assert the answer is right."""
    answer = agent(TASK)["answer"]
    ok = "30 days" in answer                                    # the eval's correctness assertion
    print("  agent answer:  %s" % answer)
    print("  eval assert 'mentions 30 days':  %s" % ("PASS ✓" if ok else "FAIL"))
    return ok


def run_faultline():
    """What faultline does: break the retrieval tool, check the agent didn't fabricate."""
    res = fl.check(
        agent, TASK,
        faults=[fl.EmptyResult(targets=["retrieve"])],         # retrieval returns nothing (rate-limited / no hits)
        invariants=[fl.abstain_when_context_empty(["retrieve"], min_chars=10)],
        trials=2,
    )
    res.report(write_md=False)
    return res


def main():
    print("=" * 70)
    print("(A) YOUR EVAL — run the agent on clean data, check the answer")
    print("=" * 70)
    eval_ok = run_plain_eval()
    print("\n  => your eval is GREEN. Looks shippable.\n")

    print("=" * 70)
    print("(B) FAULTLINE — break the retrieval tool your eval never touched")
    print("=" * 70)
    res = run_faultline()
    caught = bool(res.silent)

    print("\n" + "=" * 70)
    print("SAME AGENT. Your eval passed (it runs on clean data and never breaks the tool).")
    print("faultline broke retrieval and caught the agent fabricating '14 days' from ZERO")
    print("sources — a confident 200-OK-but-wrong your eval structurally cannot see.")
    print("That gap is the whole point. Run faultline alongside your evals, not instead of them.")
    return eval_ok, caught


if __name__ == "__main__":
    eval_ok, caught = main()
    # valid demo iff: the eval passes on clean data AND faultline catches the silent failure
    sys.exit(0 if (eval_ok and caught) else 1)
