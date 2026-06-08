"""faultline catching the real gpt-pilot empty-overwrite bug (no LLM; needs the gpt-pilot fork on PYTHONPATH).

Rule it checks: if the AI's reply comes back empty, the tool must NOT save an empty file over real
code. The REAL gpt-pilot writes the empty string straight to disk - wiping the file silently.
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock
import faultline as fl
from core.agents.code_monkey import CodeMonkey  # real, unpatched (gpt-pilot fork on main)

OLD_CODE = "def foo():\n    return 42\n"


def attempt_save(new_content):
    stub = MagicMock()
    stub.ui.send_file_status = AsyncMock(); stub.ui.generate_diff = AsyncMock()
    stub.get_line_changes = MagicMock(return_value=(0, 10))
    saved = {}
    async def _save(path, content): saved["content"] = content
    stub.state_manager.save_file = _save
    stub.state_manager.get_input_required = MagicMock(return_value=[])
    stub.step = {"save_file": {}}; stub.next_state.complete_step = MagicMock()
    asyncio.run(CodeMonkey.accept_changes(stub, "src/foo.py", OLD_CODE, new_content))
    return saved.get("content", "<save not called>")


def must_not_overwrite_with_empty(inp, out, err):
    if err is None and out == "":
        return "the file was silently overwritten with EMPTY content - the real code was lost"


fl.probe(attempt_save, fl.mutations(OLD_CODE, ("llm-reply-came-back-empty", lambda b: "")),
         [must_not_overwrite_with_empty], label="gpt-pilot: empty-overwrite guard", unpack=False).report()
