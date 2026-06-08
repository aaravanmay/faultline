"""Regression test: prep_docs must auto-generate ids when ANY doc_id is None, not just the first.

prep_docs harvested doc_ids from the Document objects and only checked doc_ids[0]. If the first
doc had a valid id but a later doc had doc_id=None (a common case from vector-store retrieval or
hand-built lists), the None id silently survived into the returned Documents and then broke
id-based lookups (RankedResults.get_score_by_docid / get_result_by_docid return None for it).

  with the fix -> PASS (all ids non-None)
  without it   -> FAIL (None survives at the later position)
"""
from rerankers.documents import Document
from rerankers.utils import prep_docs


def test_partial_none_doc_ids_are_regenerated():
    docs = [
        Document("A", doc_id="a"),
        Document("B", doc_id=None),   # later doc missing its id
        Document("C", doc_id="c"),
    ]
    out = prep_docs(docs, doc_ids=None)
    ids = [d.doc_id for d in out]
    assert None not in ids, ids
