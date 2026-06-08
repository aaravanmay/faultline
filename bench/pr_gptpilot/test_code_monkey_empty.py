"""Regression test: CodeMonkey.accept_changes must not overwrite a file with empty content.

When the model's reply is truncated or parsed to "" (OptionalCodeBlockParser returns "" for
an empty/fence-only response), accept_changes was called with new_content="" and saved it,
wiping the whole file. The run()'s `if not data` check doesn't catch it (the dict is truthy).

Calls accept_changes via the unbound method with a mock self, so no full agent/config setup:
  with the fix -> PASS (refuses, never calls save_file)
  without it   -> FAIL (calls save_file with "")
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.agents.code_monkey import CodeMonkey


@pytest.mark.asyncio
async def test_accept_changes_refuses_empty_overwrite():
    stub = MagicMock()
    stub.ui.send_file_status = AsyncMock()
    stub.ui.generate_diff = AsyncMock()
    stub.get_line_changes = MagicMock(return_value=(0, 10))
    stub.state_manager.save_file = AsyncMock()
    stub.state_manager.get_input_required = MagicMock(return_value=[])
    stub.step = {"save_file": {}}
    stub.next_state.complete_step = MagicMock()

    await CodeMonkey.accept_changes(
        stub, file_path="src/foo.py",
        old_content="def foo():\n    return 42\n", new_content="",
    )
    stub.state_manager.save_file.assert_not_called()

