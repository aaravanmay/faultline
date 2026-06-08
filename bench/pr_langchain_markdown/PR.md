# PR to LangChain (langchain-ai) — "Preserve content after an unterminated markdown code fence"

**Repo:** https://github.com/langchain-ai/langchain  (138.7k★, active — pushed 2026-06-07)
**Package:** `langchain-text-splitters`
**Fork branch (pushed):** https://github.com/langchain-ai/langchain/compare/master...aaravanmay:langchain:preserve-unterminated-code-fence
**Status:** FILED — PR #37964 (open).
*(Note: langchain's default branch is `master`, not `main` — the compare URL uses `master`.)*

## What it fixes
`ExperimentalMarkdownSyntaxTextSplitter._resolve_code_chunk`
(`libs/text-splitters/langchain_text_splitters/markdown.py`) handles a markdown code fence by
consuming lines until it finds the closing fence:

```python
def _resolve_code_chunk(self, current_line: str, raw_lines: list[str]) -> str:
    chunk = current_line
    while raw_lines:
        raw_line = raw_lines.pop(0)
        chunk += raw_line
        if self._match_code(raw_line):
            return chunk
    return ""          # <-- no closing fence: returns "" after draining ALL remaining lines
```

When the code block is **never closed**, the loop `pop(0)`s **every remaining line** off
`raw_lines` and then returns `""`. That empty chunk is dropped by `_complete_chunk_doc`, and
because `raw_lines` is now empty the outer `split_text` loop ends. Net effect: **everything
after the opening fence — including later headers and their bodies — silently disappears**, with
no error, warning, or log. `split_text` just returns a shorter, plausible-looking list of
Documents.

**Realistic fault:** unterminated/truncated code fences are common — LLM output cut at
`max_tokens` mid code block, a truncated stream, or a malformed README. RAG pipelines feed
exactly this into the header splitter.

Verified against the **real released library**: input
`"# Title\nintro\n\n\`\`\`python\nx = 1\n\n## Important Section\ncritical content\n"` →
on `master` the splitter returns only `"# Title\nintro\n\n"` (the code block and the entire
following section are gone).

## The fix — `markdown.py`
Return the accumulated content instead of `""` when the fence never closes:

```python
        # No closing fence was found: keep the accumulated content instead of returning ""
        # and silently discarding everything after the opening fence.
        return chunk
```

## The test — `libs/text-splitters/tests/unit_tests/test_markdown_unterminated_fence.py`
Feeds an unterminated ```` ```python ```` block followed by a `## Important Section`; asserts the
following content is retained. No LLM.

**Verified:** with the fix → **PASS**; on `master` → **FAIL**
(`assert 'critical content' in '# Title\nintro\n\n'`).

## Friendly PR title + body
**Title:** text-splitters: don't drop content after an unterminated markdown code fence

**Body:**
> `ExperimentalMarkdownSyntaxTextSplitter._resolve_code_chunk` returns `""` when a code fence
> is never closed, after consuming the rest of the input — so `split_text` silently discards the
> code block *and every following section/body*. This is easy to hit with truncated LLM output
> or a malformed file, and there's no error or warning.
>
> This returns the accumulated chunk instead of `""` when the fence doesn't close. Includes a
> regression test that fails on `master` and passes with the change.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"** (base branch = `master`).
2. Paste the title + body. Submit.
3. (Re-check `_resolve_code_chunk` still matches current `master` first.)
