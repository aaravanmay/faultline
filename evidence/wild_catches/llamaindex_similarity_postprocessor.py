"""DEMONSTRATION — faultline's invariant fires on a real LlamaIndex postprocessor pipeline.

STATUS / HONESTY (read first): this is a DEMONSTRATION that a faultline invariant fires on a
REAL LlamaIndex `SimilarityPostprocessor` (llama-index-core 0.14) when the node scores it filters
on are corrupted upstream. It is NOT a fileable LlamaIndex bug — a postprocessor faithfully
filtering on the scores it's given is working as designed; the failure is that a corrupted score
upstream silently changes which context survives, and a downstream answer is produced anyway with
no error. Keep this in the "demonstrated on real library code" bucket; never claim it as "a bug
found in LlamaIndex," and never fuse it with the 85-case 97.5/2.2 benchmark (those are
deterministic-Python only).

DETERMINISTIC. No LLM, no API key. Runs in CI.

What it shows
-------------
A RAG pipeline scores candidate documents, keeps the ones above a similarity cutoff via the REAL
`SimilarityPostprocessor.postprocess_nodes`, then answers. faultline wraps the scoring tool and
injects `WrongNumber` (a plausible-but-wrong score, e.g. a miscalibrated reranker). The cutoff
then drops the *wrong* documents — silently — and the pipeline answers from corrupted/empty
context with no error. The invariant `grounded_answer_needs_context` fires.

Run:  pip install faultline llama-index-core  &&  .venv311/bin/python this_file.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    from llama_index.core.postprocessor import SimilarityPostprocessor
    from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode
except Exception as exc:  # noqa: BLE001
    print("SKIPPED — llama-index-core not importable (needs Python 3.10+): %s" % exc)
    print("0 passed, 0 failed")
    sys.exit(0)

import faultline as fl

CUTOFF = 0.5
# 4 candidate docs; 2 are genuinely relevant (score >= 0.5).
_DOCS = [
    {"text": "Paris is the capital of France.", "score": 0.92},
    {"text": "France is in western Europe.", "score": 0.71},
    {"text": "Bananas are a fruit.", "score": 0.18},
    {"text": "The sky is blue.", "score": 0.11},
]


@fl.tool
def score_documents(query):
    """A reranker/embedding step: returns candidate docs with similarity scores."""
    return [dict(d) for d in _DOCS]


def rag_pipeline(task):
    scored = score_documents(task["query"])
    nodes = [NodeWithScore(node=TextNode(text=d["text"]), score=d["score"]) for d in scored]
    kept = SimilarityPostprocessor(similarity_cutoff=CUTOFF).postprocess_nodes(
        nodes, query_bundle=QueryBundle(task["query"]))
    # a stub synthesizer that always answers confidently (no LLM) — the point is that it does NOT
    # abstain when its context silently vanished.
    answer = "Based on the retrieved documents, the answer is confirmed."
    return {"answer": answer, "n_context": len(kept),
            "context": [n.node.text for n in kept]}


def grounded_answer_needs_context(run):
    """If the pipeline produced a confident answer with ZERO surviving context, that's an
    ungrounded answer — the silent failure."""
    out = run.get("output") or {}
    if out.get("answer") and out.get("n_context", 0) == 0:
        return ("produced a confident answer with 0 surviving context documents — "
                "the similarity filter silently dropped everything on corrupted scores")


def run():
    # WrongNumber(0.2): a miscalibrated reranker under-scores every doc (0.92 -> 0.18 ...),
    # so the real SimilarityPostprocessor keeps nothing — but the pipeline answers anyway.
    result = fl.check(
        rag_pipeline, {"query": "What is the capital of France?"},
        faults=[fl.WrongNumber(factor=0.2, targets=["score_documents"])],
        invariants=[grounded_answer_needs_context],
        trials=3,
    )
    result.report()
    return result


if __name__ == "__main__":
    res = run()
    bad = [r for r in res.rows if r["verdict"] in ("FAIL", "CRASH")]
    print("\nDEMONSTRATION RESULT:", "invariant fired (silent context loss caught)" if bad
          else "no catch")
    sys.exit(1 if bad else 0)
