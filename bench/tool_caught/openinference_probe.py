"""faultline mode-2 catching the real OpenInference token-count-as-cost bug. No LLM, real pip library.

Rule it checks: a token COUNT must never be recorded under a dollar-COST attribute. The tool gives
the recorder a model response that includes completion text-tokens and sees the REAL OpenInference
litellm instrumentation write that count under `llm.cost.completion_details.output` - so a cost
dashboard would read it as dollars.
"""
from types import SimpleNamespace
import faultline as fl
from openinference.instrumentation.litellm import _set_token_counts_from_usage  # REAL released, unpatched
from openinference.semconv.trace import SpanAttributes

COST_ATTR = SpanAttributes.LLM_COST_COMPLETION_DETAILS_OUTPUT  # "llm.cost.completion_details.output" (USD)


class FakeSpan:
    def __init__(self): self.attrs = {}
    def set_attribute(self, k, v): self.attrs[k] = v


def record_usage(text_tokens):
    span = FakeSpan()
    usage = SimpleNamespace(
        prompt_tokens=None, completion_tokens=None, total_tokens=None,
        completion_tokens_details=SimpleNamespace(text_tokens=text_tokens, reasoning_tokens=None, audio_tokens=None),
    )
    _set_token_counts_from_usage(span, SimpleNamespace(usage=usage))
    return span.attrs


def no_count_under_a_cost_attr(inp, out, err):
    if err is None and COST_ATTR in out:
        return "a token count (%r) was recorded under the dollar-cost attribute %r" % (out[COST_ATTR], COST_ATTR)


cases = fl.mutations(None, ("model-returns-500-text-tokens", lambda b: 500))
fl.probe(record_usage, cases, [no_count_under_a_cost_attr],
         label="OpenInference: token count vs $ cost field", unpack=False).report()
