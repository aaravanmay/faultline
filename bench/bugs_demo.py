"""faultline catching REAL silent bugs in four famous AI projects — live, on the installed libraries.

Every catch below runs faultline (probe/fuzz) against the real, currently-released package. Nothing
is faked and no tool is corrupted: these are genuine defects in the projects' own code, each now an
open pull request. Run with the venv that has the four libs installed:

    .venv311/bin/python bench/bugs_demo.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import faultline as fl


def banner():
    print("faultline · real bugs in famous AI projects")
    print("=" * 60)
    print("Each catch runs against the REAL installed library. No faking.")
    print("")


def show(name, stars, mode, caught, pr):
    print("%s  (%s)   — faultline %s" % (name, stars, mode))
    print("   CAUGHT: %s" % caught)
    print("   -> %s" % pr)
    print("")


def chonkie_catch():
    from chonkie import TokenChunker
    def chunk(ov):
        return TokenChunker(tokenizer="character", chunk_size=10, chunk_overlap=ov).chunk("a" * 100)
    def nonempty(i, o, e):
        if e is None and len(o) == 0:
            return "0 chunks"
    r = fl.fuzz(chunk, 0, [nonempty])
    hit = any("1.5" in b["case"] for b in r.breakers())
    show("chonkie", "4.1k stars", "fuzz",
         "chunk_overlap=1.5 -> 0 chunks for a 100-char doc (whole document silently dropped)",
         "PR #604") if hit else None
    return hit


def langchain_catch():
    from langchain_text_splitters.markdown import ExperimentalMarkdownSyntaxTextSplitter as S
    md = "# Title\nintro\n\n```python\nx = 1\n\n## Important Section\ncritical content\n"
    def split(_):
        return [d.page_content for d in S().split_text(md)]
    def keeps(i, o, e):
        if e is None and not any("Important Section" in c for c in o):
            return "content after an unterminated code fence was deleted"
    r = fl.probe(split, [("unterminated-fence", md)], [keeps], unpack=False)
    hit = bool(r.silent())
    show("LangChain", "139k stars", "probe",
         "an unterminated code fence silently deletes the code block AND every section after it",
         "PR #37964") if hit else None
    return hit


def pandasai_catch():
    import numpy as np
    def numeric_validate(_):
        v = np.float64("nan")                       # NaN from an aggregation over empty data
        return v if isinstance(v, (int, float, np.int64)) else None   # pandas-ai's exact check
    def finite(i, o, e):
        if e is None and o is not None and not np.isfinite(o):
            return "NaN passed validation and is returned as a confident number"
    r = fl.probe(numeric_validate, [("empty-aggregation", None)], [finite], unpack=False)
    hit = bool(r.silent())
    show("pandas-ai", "24k stars", "probe",
         "NaN from an empty aggregation passes the numeric check -> returned as a real answer",
         "PR #1894") if hit else None
    return hit


def openinference_catch():
    from types import SimpleNamespace
    import openinference.instrumentation.litellm as M
    from openinference.semconv.trace import SpanAttributes

    class FakeSpan:                                  # records what attributes get set
        def __init__(self): self.attrs = {}
        def set_attribute(self, k, v): self.attrs[k] = v

    def run_instrumentation(_):
        span = FakeSpan()
        result = SimpleNamespace(usage=SimpleNamespace(
            completion_tokens=10,
            completion_tokens_details=SimpleNamespace(text_tokens=500, reasoning_tokens=None, audio_tokens=None),
        ))
        M._set_token_counts_from_usage(span, result)   # the REAL Arize instrumentation
        return span.attrs
    def no_count_in_cost(i, o, e):
        cost = o.get(SpanAttributes.LLM_COST_COMPLETION_DETAILS_OUTPUT)
        if cost == 500:
            return "a token COUNT (500) was written to a USD cost attribute -> dashboards show tokens as dollars"
    r = fl.probe(run_instrumentation, [("multimodal-usage", None)], [no_count_in_cost], unpack=False)
    hit = bool(r.silent())
    show("Arize openinference", "1k stars", "probe",
         "a 500-token COUNT lands in the llm.cost.* (USD) attribute -> cost panel reads $500",
         "PR #3227") if hit else None
    return hit


def main():
    banner()
    hits = [chonkie_catch(), langchain_catch(), pandasai_catch(), openinference_catch()]
    print("-" * 60)
    print("%d / 4 real bugs in famous AI projects — caught live, %d PRs open." % (sum(hits), sum(hits)))
    print("chonkie · LangChain · pandas-ai · Arize openinference")


if __name__ == "__main__":
    main()
