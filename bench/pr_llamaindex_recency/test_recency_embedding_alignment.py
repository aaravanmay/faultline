"""Regression test: EmbeddingRecencyPostprocessor must align text embeddings with sorted_nodes.

The dedup loop indexes text_embeddings[idx2] where idx2 walks the date-SORTED node list, but
text_embeddings was built in the ORIGINAL node order. When the input isn't already date-sorted
(the normal case — retrievers return relevance order), the near-duplicate check compares the
query against the wrong node's embedding and silently drops the wrong nodes.

Deterministic, no live LLM: a fake embedder maps "alpha"->x, "bravo"->y (orthogonal).
n0 and n2 are true duplicates ("alpha"); n1 ("bravo") is unique. Input order is not
date-sorted. Correct behavior keeps the newest of the duplicates (n0) + the unique node (n1)
and drops the older duplicate (n2) -> {n0, n1}. The misindexing instead drops the UNIQUE
node n1 -> {n0}.

  with the fix -> PASS (survivors == {n0, n1})
  without it   -> FAIL (survivors == {n0})
"""
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.postprocessor.node_recency import EmbeddingRecencyPostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode


class FakeEmbed(BaseEmbedding):
    @staticmethod
    def _vec(text):
        if "alpha" in text:
            return [1.0, 0.0, 0.0]
        if "bravo" in text:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 0.0]

    def _get_query_embedding(self, query):
        return self._vec(query)

    def _get_text_embedding(self, text):
        return self._vec(text)

    async def _aget_query_embedding(self, query):
        return self._vec(query)

    async def _aget_text_embedding(self, text):
        return self._vec(text)


def _node(id_, text, date):
    return NodeWithScore(node=TextNode(id_=id_, text=text, metadata={"date": date}))


def test_recency_dedup_uses_aligned_embeddings():
    # original order is NOT date-sorted (n1 first); n0 & n2 are duplicates ("alpha")
    nodes = [
        _node("n1", "bravo", "2023-01-01"),
        _node("n0", "alpha", "2024-01-01"),  # newest
        _node("n2", "alpha", "2022-01-01"),  # older duplicate of n0
    ]
    pp = EmbeddingRecencyPostprocessor(embed_model=FakeEmbed(), similarity_cutoff=0.5)
    out = pp.postprocess_nodes(nodes, query_bundle=QueryBundle(query_str="q"))
    ids = {n.node.node_id for n in out}
    assert ids == {"n0", "n1"}, ids
