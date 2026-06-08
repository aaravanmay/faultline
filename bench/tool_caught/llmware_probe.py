"""faultline catching the real llmware context-expander bug (no LLM; needs the llmware fork on PYTHONPATH).

Rule it checks: when expanding context backwards, the tool must walk through DIFFERENT blocks, not
re-look-up the same one. The REAL llmware re-reads the same block over and over (duplicated/stuck
context) because it never advances its counter.
"""
import faultline as fl
from llmware.retrieval import Query  # real, unpatched (run with the llmware fork checked out on main)


class StubQuery:
    def __init__(self):
        self.calls = []
        self.blocks = {i: {"block_ID": i, "doc_ID": 1, "text": "x" * 50} for i in range(5)}
    def block_lookup(self, block_id, doc_id):
        self.calls.append(block_id)
        if len(self.calls) > 200:
            raise RuntimeError("infinite loop: block_id never advanced")
        return self.blocks.get(block_id)


def expand_context_before(start_block):
    sq = StubQuery()
    Query.expand_text_result_before(sq, {"block_ID": start_block, "doc_ID": 1})
    return sq.calls


def must_walk_distinct_blocks(inp, out, err):
    if err is None and len(set(out)) <= 1:
        return "the expander re-looked-up the same block %d times instead of walking distinct blocks (stuck/duplicated context)" % len(out)


fl.probe(expand_context_before, [("expand-back-from-a-hit", 5)], [must_walk_distinct_blocks],
         label="llmware: context expander walks distinct blocks", unpack=False).report()
