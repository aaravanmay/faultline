"""Regression test: chunk_by_sentence must raise on an oversized word mid-stream, not only last.

The docstring promises a ValueError if an individual word exceeds maximum_size. The trailing
path raises, but the main loop silently yielded an over-budget chunk (sentence_size >
maximum_size) when an oversized token appeared anywhere except the last position - and that
chunk then flows through chunk_by_paragraph into embeddings with no error.

get_word_size is stubbed (size = char length) so the test needs no embedding engine / LLM.

  with the fix -> PASS (raises ValueError, like the documented contract + the tail path)
  without it   -> FAIL (silently yields a chunk whose size exceeds maximum_size)
"""
import pytest

import cognee.tasks.chunks.chunk_by_sentence as m


def test_oversized_word_midstream_raises(monkeypatch):
    monkeypatch.setattr(m, "get_word_size", lambda w, *a, **k: len(w))
    # "supercalifragilistic" (len 20 > 5) is NOT in the last position.
    with pytest.raises(ValueError):
        list(m.chunk_by_sentence("hi supercalifragilistic ok done", maximum_size=5))
