"""faultline demo — catch a SILENT failure an LLM-judge would miss.

No network, no API keys, runs in ~1 second. It models the EXACT bug we found and fixed in
three real, famous agents — GPT Researcher (PR #1799), STORM, and LlamaIndex — where the
report writer answers confidently from EMPTY retrieval, fabricating a "sourced" answer.

The point faultline makes that an eval/LLM-judge does not:
  * On good data the agent answers correctly  -> looks fine in every eval.
  * Break ONLY the retrieval tool (it returns nothing, like a rate-limit/bot-block) and the
    agent STILL returns a confident answer, with no error and no uncertainty.
  * That "200 OK but wrong" is invisible to a pass/fail eval on clean data. faultline's
    deterministic invariant (abstain_when_context_empty) catches it every time.

Run:  python3 examples/demo_silent_rag.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import faultline as fl


# --- a tiny knowledge base + a "research assistant" agent ---------------------
KB = {
    "eiffel tower": "The Eiffel Tower was completed in 1889 for the World's Fair in Paris.",
}


@fl.tool
def search(query):
    """Retrieve source snippets for the query. faultline may break this."""
    for key, doc in KB.items():
        if key in query.lower():
            return [doc]
    return []


def _write_report(query, context):
    """Stand-in for the report LLM. Like a real model, when handed EMPTY context it does
    NOT refuse — it answers confidently from its priors (the exact silent failure)."""
    if context:
        return "Based on the sources: " + " ".join(context)
    # no context -> fabricate, just like GPT Researcher / STORM / LlamaIndex did: a long,
    # confident, "cited" report invented from the model's priors — and WRONG (it was 1889).
    return (
        "The Eiffel Tower was completed in 1887 after roughly three years of construction "
        "and was financed primarily by the French government as a permanent monument [1]. "
        "Designed by Gustave Eiffel's firm, it rises 324 meters and was the tallest "
        "structure in Europe at the time of its opening [2]. Contemporary records indicate "
        "it drew over five million visitors in its first year of operation [3]. The tower "
        "was originally painted a deep red before being repainted in its now-iconic bronze "
        "tone in the early 1890s [4]."
    )


def research_agent(task):
    snippets = search(task)
    report = _write_report(task, snippets)
    return {"report": report}


# --- run faultline -----------------------------------------------------------
def main():
    print("=" * 72)
    print("faultline demo — empty-retrieval fabrication (real bug in 3 famous agents)")
    print("=" * 72)

    # Baseline: with real retrieval, the agent is correct — every eval is happy.
    baseline = research_agent("When was the Eiffel Tower completed?")
    print("\n[baseline, real data]  ", baseline["report"][:90], "...")

    # The invariant: if ALL retrieval came back empty, the answer must abstain.
    inv = fl.abstain_when_context_empty(tools=["search"])

    res = fl.check(
        research_agent,
        task="When was the Eiffel Tower completed?",
        faults=[
            fl.NullResponse(targets=["search"]),   # retrieval returns nothing (rate-limit/block)
            fl.Truncate(targets=["search"]),        # retrieval returns a truncated fragment
        ],
        invariants=[inv],
        trials=3,
    )

    print()
    res.report()
    print("\nTakeaway: the agent passed on clean data, but under a broken retriever it")
    print("fabricated a confident, 'cited', WRONG answer with NO error. faultline's")
    print("deterministic invariant caught it — that is the 200-OK-but-wrong failure")
    print("LLM-judges and clean-data evals miss. We filed the real fix as GPT Researcher #1799.")


if __name__ == "__main__":
    main()
