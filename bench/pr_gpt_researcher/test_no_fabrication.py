"""Regression test for the GPT Researcher PR: don't fabricate a report when no
research content was gathered.

When every retriever returns empty (rate-limited, blocked, or genuinely no hits),
`ReportGenerator.write_report` still calls the report LLM, which produces a
confident, sourced-looking report from its own priors (it even invents citations).
A research tool should abstain instead.

This test mocks the report LLM (`generate_report`) so it needs NO API call:
  with the fix  -> PASS  (empty context -> abstains, never calls generate_report)
  without it    -> FAIL  (calls generate_report and returns the fabricated text)

Drop into gpt-researcher's suite (e.g. tests/report/test_empty_context.py).
"""
import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from gpt_researcher.skills.writer import ReportGenerator


def _stub_researcher(context):
    return SimpleNamespace(
        query="What year was the Eiffel Tower completed?",
        role="research assistant",
        report_type="research_report",
        report_source="web",
        tone="objective",
        websocket=None,
        headers={},
        cfg=SimpleNamespace(agent_role=None),
        verbose=False,
        context=context,
        get_research_images=lambda: [],
        add_costs=lambda *a, **k: None,
        kwargs={},
    )


class TestNoFabricationOnEmptyContext(unittest.TestCase):
    def test_empty_context_abstains_not_fabricates(self):
        gen = ReportGenerator(_stub_researcher([]))      # zero research content
        with patch(
            "gpt_researcher.skills.writer.generate_report",
            new=AsyncMock(return_value="FABRICATED CONFIDENT REPORT"),
        ) as gen_report:
            report = asyncio.run(gen.write_report())

        gen_report.assert_not_called()                   # did NOT call the LLM to fabricate
        self.assertNotIn("FABRICATED", report)
        self.assertTrue(
            any(w in report.lower() for w in
                ("couldn't", "could not", "no source", "not able", "no research")),
            f"expected an abstention, got: {report[:120]!r}",
        )


if __name__ == "__main__":
    unittest.main()
