# PR to cover-agent / qodo-cover (qodo-ai) — "Raise on a stale coverage report instead of only warning"

**Repo:** https://github.com/qodo-ai/qodo-cover  (formerly Codium-ai/cover-agent, ~5k★)
**Fork branch (pushed):** https://github.com/qodo-ai/qodo-cover/compare/main...aaravanmay:qodo-cover:raise-on-stale-coverage-report
**Status:** STAGED — fork pushed, verified. NOT filed yet (Aarav to review + click "Create PR").
*(Double-check the upstream default branch name in the compare URL — it may be `main`.)*

## What it fixes
`CoverageProcessor.verify_report_update` (`cover_agent/coverage_processor.py`) is documented
to **raise** when the coverage report wasn't refreshed by the test run:

> `Raises: AssertionError: If the coverage report does not exist or was not updated after the test command.`

But the implementation only calls `self.logger.warning(...)` and returns. So when the report
on disk is **stale** (two runs within the filesystem's 1-second mtime resolution; a fast test
that exits 0 without regenerating coverage; a cached CI artifact), `process_coverage_report`
goes on to parse the *old* report, and the caller (`UnitTestValidator.validate_test`) compares
that stale coverage to the baseline and **silently rolls back the newly generated test** as
"coverage did not increase" — with no hint the report was stale. A real silent failure: the
agent discards good work for the wrong reason.

## The fix — `cover_agent/coverage_processor.py`
Replace the warning-only branch with the `AssertionError` the docstring already promises
(matching the `assert os.path.exists(...)` on the line above):

```python
        if not file_mod_time_ms > time_of_test_command:
            raise AssertionError(
                f"Fatal: The coverage report file was not updated after the test command. "
                f"file_mod_time_ms: {file_mod_time_ms}, time_of_test_command: {time_of_test_command}."
            )
```

## The test — `tests/test_stale_coverage_report.py` (in the fork)
Writes a tmp report, calls `verify_report_update` with a test-command time *after* the report's
mtime (so it's stale), asserts it raises. Uses the unbound method with a mock self (only
`file_path`/`logger` are touched), so no full run.

**Verified:** with the fix → **PASS**; on `main` → **FAIL** (`DID NOT RAISE`).

## Friendly PR title + body
**Title:** Raise on a stale coverage report instead of only logging a warning

**Body:**
> `verify_report_update`'s docstring says it raises `AssertionError` when the coverage report
> wasn't updated after the test command, but the code only logs a warning and returns. So a
> stale report (same-second mtime, a cached artifact, a fast no-op test run) is parsed anyway,
> and the newly generated test gets silently rolled back as "coverage did not increase" — with
> no sign the report was stale.
>
> This raises `AssertionError` on a stale report, matching the docstring and the existing
> `assert` above it. Includes a regression test (mock self, no real run) that fails on `main`
> and passes with the change. Happy to make it a softer signal (return value/flag) if you'd
> prefer not to raise.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"** (confirm the base branch).
2. Paste the title + body. Submit.
3. (Re-check the function still matches current upstream first.)
