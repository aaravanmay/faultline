"""faultline GENUINELY catching the real rerankers None-doc_id bug (no LLM, the REAL library).

Run:  python3 bench/tool_caught/rerankers_none_id.py

A RAG agent retrieves documents through a tool and prepares them with rerankers' REAL prep_docs.
faultline injects a realistic fault (one retrieved hit came back without its id) and an invariant
flags the None id that real prep_docs silently let through - which then breaks id-based score
lookups. The tool catches it.
"""
import faultline as fl
from rerankers.documents import Document
from rerankers.utils import prep_docs  # the REAL released rerankers (unpatched)


@fl.tool
def retrieve(query):
    """Vector retrieval. faultline is allowed to break this."""
    return [
        Document("doc about A", doc_id="a"),
        Document("doc about B", doc_id="b"),
        Document("doc about C", doc_id="c"),
    ]


def rag_agent(task):
    docs = retrieve(task)
    prepped = prep_docs(docs, doc_ids=None)         # REAL rerankers (the buggy function)
    return {"doc_ids": [d.doc_id for d in prepped]}


class DropId(fl.Fault):
    """Realistic fault: a retrieved hit came back missing its id (a vector store returned a
    match whose metadata id was dropped). Null a non-first doc's id."""
    name = "drop-id"

    def hit(self, tool_name, args, kwargs, result):
        if isinstance(result, list) and len(result) > 1:
            result[1].doc_id = None
        return result


def no_null_doc_id(run):
    out = run.get("output")
    if out and None in out.get("doc_ids", []):
        return "a None doc_id survived prep_docs - id-based score lookups will silently return 'not found'"


if __name__ == "__main__":
    res = fl.check(
        rag_agent,
        task="some query",
        faults=[DropId(targets=["retrieve"])],
        invariants=[no_null_doc_id],
        trials=3,
    )
    res.report()
