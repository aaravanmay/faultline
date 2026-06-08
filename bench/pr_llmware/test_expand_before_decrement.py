"""Regression test: expand_text_result_before must walk backwards through blocks.

The while loop never decremented block_id, so it re-looked-up the SAME preceding block
forever - duplicating that block's text until window_size (garbage context), or hanging
forever if that block_lookup returned None. The sibling expand_text_result_after decrements
correctly. This walks block_id down to 0 like _after walks it up.

Calls the method via the unbound method with a stub self (only block_lookup is used), so no
DB/account/LLM. The stub raises after 200 calls so a regression can't hang CI.

  with the fix -> PASS (looks up blocks 4,3,2,1,0 once each, in order)
  without it   -> FAIL (re-looks-up block 4 repeatedly)
"""
import pytest

from llmware.retrieval import Query


class StubQuery:
    def __init__(self):
        self.calls = []
        self.blocks = {i: {"block_ID": i, "doc_ID": 1, "text": "x" * 50} for i in range(5)}

    def block_lookup(self, block_id, doc_id):
        self.calls.append(block_id)
        if len(self.calls) > 200:
            raise RuntimeError("expand_text_result_before never advanced block_id (infinite loop)")
        return self.blocks.get(block_id)


def test_expand_before_walks_backwards():
    sq = StubQuery()
    out = Query.expand_text_result_before(sq, {"block_ID": 5, "doc_ID": 1})
    assert sq.calls == [4, 3, 2, 1, 0], sq.calls
    assert [b["block_ID"] for b in out["results"]] == [4, 3, 2, 1, 0]
