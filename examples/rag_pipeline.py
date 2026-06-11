"""Drop faultline into YOUR RAG pipeline — a copy-paste integration template.

The #1 RAG silent failure: retrieval comes back EMPTY (rate-limited, bot-blocked, no hits) and
the generator answers confidently from its priors anyway — a fabricated "sourced" answer. We found
and fixed exactly this in GPT-Researcher (PR #1799), STORM, and LlamaIndex. An eval on good data
passes it every time; faultline's deterministic `abstain_when_context_empty` catches it.

To use this on YOUR pipeline: replace `retrieve` and `generate` with your real retriever + LLM call,
keep the faultline suite, and run it in CI. No API key needed here (generate() is a stand-in).

    python3 examples/rag_pipeline.py        # watch it catch the buggy generator
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import faultline as fl

# A tiny stand-in knowledge base. Replace `retrieve` with your real vector search / search API.
_KB = {"refund window": "Our refund window is 30 days from purchase."}


@fl.tool
def retrieve(query):
    """YOUR retriever. Returns a list of source chunks. faultline will break this."""
    return [doc for key, doc in _KB.items() if key in query.lower()]


def generate_buggy(query, docs):
    """A generator that ANSWERS even with no sources — the silent failure."""
    if docs:
        return "Per our docs: " + " ".join(docs)
    return "Per our docs, the refund window is 14 days."        # fabricated from priors


def generate_grounded(query, docs):
    """The fix: abstain when there are no sources."""
    if not docs:
        return "I couldn't find anything in our sources about that."
    return "Per our docs: " + " ".join(docs)


def _rag(generate):
    def rag(task):
        docs = retrieve(task["query"])
        return {"answer": generate(task["query"], docs)}
    return rag


# The rule: if retrieval came back empty, the answer must abstain (not fabricate).
GROUNDED = fl.abstain_when_context_empty(["retrieve"], min_chars=10)
TASK = {"query": "what is the refund window?"}
# Break retrieval the way reality does: empty result, or nothing at all.
FAULTS = [fl.EmptyResult(targets=["retrieve"]), fl.NullResponse(targets=["retrieve"])]


def faultline_check():
    """Drop this into CI: returns the faultline Result for the (buggy) pipeline."""
    return fl.check(_rag(generate_buggy), TASK, faults=FAULTS, invariants=[GROUNDED], trials=2)


def main():
    print("RAG pipeline · faultline integration template\n" + "=" * 60)
    print("\n[A] buggy generator (answers even with zero sources):")
    bad = fl.check(_rag(generate_buggy), TASK, faults=FAULTS, invariants=[GROUNDED], trials=2)
    bad.report(write_md=False)

    print("\n[B] grounded generator (abstains on empty retrieval):")
    good = fl.check(_rag(generate_grounded), TASK, faults=FAULTS, invariants=[GROUNDED], trials=2)
    good.report(write_md=False)

    print("\n" + "=" * 60)
    print("The buggy pipeline fabricated a 'sourced' answer from nothing — caught deterministically,")
    print("no LLM judge. The grounded one abstained and passed. Swap in your retriever + LLM and run in CI.")
    return bad, good


if __name__ == "__main__":
    bad, good = main()
    sys.exit(0 if (bad.silent and not good.silent) else 1)
