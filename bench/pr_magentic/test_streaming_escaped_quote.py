"""Regression test: a streamed JSON array with an escaped quote must not yield zero elements.

JsonArrayParserState never tracked backslash escapes while inside a string, so an escaped
quote (\\") was treated as the closing quote - desyncing the parser so iter_streamed_json_array
silently yielded NO elements for perfectly valid JSON like ["he said \\"hi\\"", "bye"].

  with the fix -> PASS (2 elements, round-trip correct)
  without it   -> FAIL (0 elements)
"""
import json

from magentic.streaming import iter_streamed_json_array


def test_escaped_quote_in_streamed_array():
    payload = json.dumps(['he said "hi"', "bye"])   # '["he said \\"hi\\"", "bye"]'
    elements = list(iter_streamed_json_array([payload]))
    assert len(elements) == 2, elements
    assert [json.loads(e) for e in elements] == ['he said "hi"', "bye"]
