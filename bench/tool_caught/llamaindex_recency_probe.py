"""faultline mode-2 catching the real LlamaIndex recency-dedup bug. No LLM, real library.

Rule it checks: which documents survive de-duplication must NOT depend on the order they came
in (the function sorts by date internally, so input order shouldn't matter). The tool reverses
the input order and sees the REAL LlamaIndex keep a DIFFERENT set of documents - silently wrong.
"""
from unittest.mock import MagicMock
import faultline as fl
from llama_index.core.base.embeddings.base import BaseEmbedding
from llama_index.core.postprocessor.node_recency import EmbeddingRecencyPostprocessor
from llama_index.core.schema import NodeWithScore, QueryBundle, TextNode


class FakeEmbed(BaseEmbedding):
    @staticmethod
    def _v(t): return [1.0,0,0] if "alpha" in t else ([0,1.0,0] if "bravo" in t else [0,0,0])
    def _get_query_embedding(self, q): return self._v(q)
    def _get_text_embedding(self, t): return self._v(t)
    async def _aget_query_embedding(self, q): return self._v(q)
    async def _aget_text_embedding(self, t): return self._v(t)


def survivors(nodes):
    pp = EmbeddingRecencyPostprocessor(embed_model=FakeEmbed(), similarity_cutoff=0.5)
    out = pp.postprocess_nodes(list(nodes), query_bundle=QueryBundle(query_str="q"))
    return {n.node.node_id for n in out}


def _nodes():
    return [
        NodeWithScore(node=TextNode(id_="n1", text="bravo", metadata={"date": "2023-01-01"})),
        NodeWithScore(node=TextNode(id_="n0", text="alpha", metadata={"date": "2024-01-01"})),
        NodeWithScore(node=TextNode(id_="n2", text="alpha", metadata={"date": "2022-01-01"})),
    ]


baseline = survivors(_nodes())

def order_must_not_change_survivors(inp, out, err):
    if err is None and out != baseline:
        return "reversing the input order changed which documents survived (%s vs %s) - dedup is order-dependent" % (sorted(out), sorted(baseline))

fl.probe(survivors,
         [("reversed-input-order", list(reversed(_nodes())))],
         [order_must_not_change_survivors],
         label="LlamaIndex recency: order invariance", unpack=False).report()
