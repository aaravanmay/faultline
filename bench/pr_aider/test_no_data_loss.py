"""Regression test for the Aider PR: a drastic whole-file shrink must not be
written silently (it's almost always data loss from incomplete context).

Drop this into aider's suite as tests/basic/test_wholefile_no_data_loss.py.
It needs NO LLM call — it calls apply_edits() directly with a shrinking edit,
which is exactly the code path the fix guards.

  with the fix  -> PASS  (apply_edits asks before overwriting; file preserved)
  without it    -> FAIL  (file silently clobbered down to 2 lines)
"""
import os
import tempfile
import unittest
from unittest.mock import patch

from aider.coders import Coder
from aider.io import InputOutput
from aider.models import Model


class TestWholeFileNoDataLoss(unittest.TestCase):
    def test_drastic_shrink_is_confirmed_not_silent(self):
        cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as d:
            os.chdir(d)                       # so the coder's root is this temp dir
            try:
                with open("mod.py", "w") as fh:
                    fh.write("".join("line%d = %d\n" % (i, i) for i in range(20)))

                io = InputOutput(yes=False)
                coder = Coder.create(
                    main_model=Model("gpt-4o"), io=io, fnames=["mod.py"],
                    edit_format="whole", use_git=False,
                )
                # a whole-file rewrite that returns only 2 of the 20 lines
                edits = [("mod.py", "chat", ["line0 = 0\n", "line1 = 1\n"])]

                with patch.object(io, "confirm_ask", return_value=False) as ask:
                    coder.apply_edits(edits)

                ask.assert_called()                                  # it asked first
                with open("mod.py") as fh:
                    self.assertEqual(len(fh.read().splitlines()), 20)  # nothing lost
            finally:
                os.chdir(cwd)


if __name__ == "__main__":
    unittest.main()
