"""faultline catching the real STORM empty-sources bug. No API key (stand-in LLM).

Rule it checks: with NO sources collected for a section, STORM must abstain - it must NOT call the
section-writing LLM to produce a "sourced" Wikipedia section anyway. The tool empties the sources and
sees the REAL STORM write a section (with citation markers pointing at nothing) from no sources.
"""
from types import SimpleNamespace
from unittest.mock import patch, MagicMock
import faultline as fl
from knowledge_storm.storm_wiki.modules.article_generation import ConvToSection  # real pip, unpatched


def write_a_section(collected_info):
    module = ConvToSection(engine=MagicMock())
    with patch.object(module, "write_section") as spy:
        spy.return_value.output = "Paris is the capital of France [1][2]."   # stand-in LLM output
        result = module.forward(topic="X", outline="", section="History", collected_info=collected_info)
    return {"llm_called": spy.called, "section": result.section}


def must_abstain_with_no_sources(inp, out, err):
    if err is None and len(inp) == 0 and out["llm_called"]:
        return "with NO sources collected, it CALLED the section-writer and produced a 'sourced' section anyway (citations point at nothing)"


cases = fl.mutations(
    [SimpleNamespace(snippets=["Paris is the capital of France."])],   # baseline: a real source
    ("no-sources-found", lambda base: []),
)
fl.probe(write_a_section, cases, [must_abstain_with_no_sources],
         label="STORM: abstain when no sources collected", unpack=False).report()
