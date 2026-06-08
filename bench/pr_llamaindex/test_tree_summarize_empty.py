"""Regression test: TreeSummarize must not call the LLM with empty context.

When get_response/aget_response receive no text chunks (a direct caller) or only blank
chunks (retrieved nodes whose content is empty), repack collapses them to [""], len==1,
and the LLM is asked to answer with context_str="" - a confident answer from no sources.
synthesize() already guards len(nodes)==0, but not these two paths.

  with the fix -> PASS (returns the standard empty response, never calls the LLM)
  without it   -> FAIL (calls the LLM with empty context)
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

from llama_index.core.llms import MockLLM
from llama_index.core.response_synthesizers.tree_summarize import TreeSummarize


def _synth():
    synth = TreeSummarize(llm=MockLLM())
    synth._llm = MagicMock()
    synth._llm.predict.return_value = "LLM ANSWERED FROM EMPTY CONTEXT"
    synth._llm.apredict = AsyncMock(return_value="LLM ANSWERED FROM EMPTY CONTEXT")
    # simulate repack's real behavior on blank input -> [""]
    synth._prompt_helper = MagicMock()
    synth._prompt_helper.repack.return_value = [""]
    synth._streaming = False
    synth._output_cls = None
    return synth


def test_empty_list_abstains():
    s = _synth()
    resp = s.get_response("q", text_chunks=[])
    s._llm.predict.assert_not_called()
    assert resp == s._empty_response


def test_all_blank_chunks_abstains():
    s = _synth()
    resp = s.get_response("q", text_chunks=["", "   "])
    s._llm.predict.assert_not_called()
    assert resp == s._empty_response


def test_async_empty_abstains():
    s = _synth()
    resp = asyncio.run(s.aget_response("q", text_chunks=[]))
    s._llm.apredict.assert_not_called()
    assert resp == s._empty_response
