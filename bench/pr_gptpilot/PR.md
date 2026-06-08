# PR to GPT Pilot (Pythagora-io) — "Refuse to overwrite a file with empty content"

**Repo:** https://github.com/Pythagora-io/gpt-pilot  (34k★)
**Fork branch (pushed):** https://github.com/Pythagora-io/gpt-pilot/compare/main...aaravanmay:gpt-pilot:refuse-empty-overwrite
**Status:** STAGED — fork pushed, verified. NOT filed yet (Aarav to review + click "Create PR").

## What it fixes
`CodeMonkey.accept_changes` (`core/agents/code_monkey.py`) writes the model's output to
disk with `state_manager.save_file(file_path, new_content)` and **no guard on
`new_content`**. When the model's reply is truncated or parses to `""` —
`OptionalCodeBlockParser` returns `""` for an empty or fence-only response (e.g. the model
hit `max_tokens` and emitted ` ```python\n``` `) — `accept_changes` is called with
`new_content=""` and **overwrites the entire file with nothing**. The `run()` method's
`if not data` check doesn't catch it, because `data` is a truthy dict. No error, no warning;
the UI even shows a diff that looks like an intentional deletion.

## The fix — `core/agents/code_monkey.py`
At the top of `accept_changes`:

```python
        if not new_content and old_content:
            log.warning(
                "Refusing to overwrite %s with empty content (the model returned nothing "
                "usable); keeping the existing file.",
                file_path,
            )
            return AgentResponse.done(self)
```

`log` is already defined at module scope. Only fires when the new content is empty **and**
the file currently has content — a legitimately-empty new file is unaffected.

## The test — `tests/agents/test_code_monkey_empty.py` (in the fork)
Calls `accept_changes` via the unbound method with a mock `self` (so no full agent/LLM/DB
setup), passing `new_content=""` over a non-empty file; asserts `save_file` is never called.

**Verified:** with the fix → **PASS**; on `main` → **FAIL** with
`save_file ... Called: [call('src/foo.py', '')]` (the file wiped).
Run: `pytest tests/agents/test_code_monkey_empty.py -o addopts=""`
(their `pyproject.toml` adds `--cov`/`--timeout`; clear addopts or install those plugins.)

## Friendly PR title + body
**Title:** Refuse to overwrite a file with empty content (avoid silent data loss)

**Body:**
> `CodeMonkey.accept_changes` saves the model's output with no check on `new_content`. When
> the reply is truncated or parses to `""` (`OptionalCodeBlockParser` returns `""` for an
> empty/fence-only response), the whole file is overwritten with nothing — `run()`'s
> `if not data` guard doesn't catch it because the dict is truthy. No error is raised.
>
> This refuses to save empty content over a non-empty file (logs a warning, returns done).
> Includes a regression test (mock self, no full agent setup) that fails on `main`
> (`save_file` called with `""`) and passes with the change.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check `accept_changes` still matches current `main` first.)
