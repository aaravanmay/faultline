"""Regression test: merging list fields across extracted JSON objects must not duplicate.

parse_response_model_str falls back to _parse_individual_json when the content isn't a single
valid JSON object - e.g. an LLM echoed/retried its structured output as two concatenated
objects. List fields were blindly .extend()ed across every object, so identical objects
doubled the list. The doubled list still validates against the schema, so it was returned
as a valid model with no error or warning (a silent failure).

  with the fix -> PASS (deduped)
  without it   -> FAIL (['ai','agents','ai','agents'])
"""
from pydantic import BaseModel

from agno.utils.string import parse_response_model_str


class Article(BaseModel):
    keywords: list[str]


def test_concatenated_duplicate_objects_not_doubled():
    content = '{"keywords": ["ai", "agents"]} {"keywords": ["ai", "agents"]}'
    out = parse_response_model_str(content, Article)
    assert out is not None
    assert out.keywords == ["ai", "agents"], out.keywords
