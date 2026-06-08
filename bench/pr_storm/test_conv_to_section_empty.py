"""Regression test: ConvToSection must not write a section from empty retrieval.

When no information is gathered for a section (empty knowledge base / no hits),
the writer should abstain rather than ask the LLM to produce a confident,
"sourced" section with citation markers pointing at nothing.

  with the fix -> PASS (abstains, never calls the section LLM)
  without it   -> FAIL (calls the LLM to write from empty info)
"""
import unittest
from unittest.mock import MagicMock, patch

from knowledge_storm.storm_wiki.modules.article_generation import ConvToSection


class TestConvToSectionEmpty(unittest.TestCase):
    def test_abstains_on_empty_collected_info(self):
        module = ConvToSection(engine=MagicMock())
        with patch.object(module, "write_section") as mock_ws:
            mock_ws.return_value.output = ""
            result = module.forward(
                topic="Some Topic", outline="", section="History", collected_info=[]
            )
        mock_ws.assert_not_called()
        self.assertEqual(result.section, "")


if __name__ == "__main__":
    unittest.main()
