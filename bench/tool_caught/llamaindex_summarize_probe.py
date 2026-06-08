"""faultline catching the real LlamaIndex TreeSummarize empty-context bug. No API key (stand-in LLM).

Rule it checks: with NO retrieved context, the summarizer must abstain - it must NOT call the LLM
to answer anyway. The tool empties the context and sees the REAL LlamaIndex call the LLM and produce
a confident answer from nothing (a fabrication waiting to happen).
"""
from unittest.mock import patch
import faultline as fl
from llama_index.core.llms import MockLLM
from llama_index.core.response_synthesizers.tree_summarize import TreeSummarize  # real pip, unpatched


def summarize(text_chunks):
    synth = TreeSummarize(llm=MockLLM(max_tokens=64))
    # stand in for ANY real LLM and record whether it gets called
    with patch.object(MockLLM, "predict", return_value="The answer is definitely 42.") as spy:
        out = synth.get_response("What is X?", text_chunks=list(text_chunks))
    return {"llm_called": spy.called, "output": str(out)}


def must_abstain_on_empty_context(inp, out, err):
    empty = (not inp) or all(not c.strip() for c in inp)
    if err is None and empty and out["llm_called"]:
        return "with NO context retrieved, it CALLED the LLM and answered anyway instead of abstaining (it returned %r)" % out["output"][:40]


cases = fl.mutations(
    ["Paris is the capital of France."],                   # real retrieved context
    ("retrieval-came-back-empty", lambda base: []),
)
fl.probe(summarize, cases, [must_abstain_on_empty_context],
         label="LlamaIndex TreeSummarize: abstain on empty context", unpack=False).report()
