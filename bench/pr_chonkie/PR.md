# PR to chonkie (chonkie-inc) — "Validate the computed chunk_overlap so a float ≥ 1.0 can't silently drop all content"

**Repo:** https://github.com/chonkie-inc/chonkie  (4.1k★, actively maintained — pushed 2026-06-07)
**Fork branch (pushed):** https://github.com/chonkie-inc/chonkie/compare/main...aaravanmay:chonkie:validate-computed-overlap
**Status:** FILED — PR #604 (open).

> **Internal note (not for the PR body):** this is the hero bug — faultline's **fuzz mode**, pointed at
> the real installed chonkie with only "chunking must never silently return 0 chunks" as the rule,
> autonomously generated 37 inputs and found `fractional-1.5 → 0 chunks` by itself. So "the tool found
> this" is literally true here. Keep the maintainer-facing body below humble and tool-agnostic anyway.

## What it fixes
`TokenChunker.__init__` (`src/chonkie/chunker/token.py`) validates the overlap with:

```python
if isinstance(chunk_overlap, int) and chunk_overlap >= chunk_size:
    raise ValueError("chunk_overlap must be less than chunk_size")
```

That guard is gated on `isinstance(chunk_overlap, int)`. But `chunk_overlap` is typed
`Union[int, float]`, and a **float** is converted to `int(chunk_overlap * chunk_size)`. So a
float `≥ 1.0` (e.g. a user who confuses the fraction form with a token count and passes
`1.5`) becomes `int(1.5 * chunk_size)`, which can be **≥ chunk_size** — and the int-only
guard never fires.

`_token_group_generator` then steps with `range(0, len(tokens), chunk_size - chunk_overlap)`.
When `chunk_overlap ≥ chunk_size` the step is **zero or negative**, so the range is empty,
`chunk()` returns `[]`, and **the entire document is silently dropped** — indexed as nothing
in a RAG pipeline, with no error. (The docstring already promises
`Raises: ValueError: If ... chunk_overlap >= chunk_size`.)

Verified locally: `TokenChunker(tokenizer="character", chunk_size=10, chunk_overlap=1.5)`
constructs with no error, and `chunk("a"*100)` returns **0 chunks**.

## The fix — `src/chonkie/chunker/token.py`
Validate the **computed** overlap (ints and floats alike), right after it's assigned:

```python
        if self.chunk_overlap >= self.chunk_size or self.chunk_overlap < 0:
            raise ValueError("chunk_overlap must be >= 0 and less than chunk_size")
```

## The test — `tests/test_token_overlap_validation.py` (in the fork)
- `chunk_overlap=1.5` → raises `ValueError` (no silent drop).
- `chunk_overlap=0.1` → still chunks normally (the fix doesn't over-reject valid fractions).
Uses the default `"character"` tokenizer — no model download, no LLM.

**Verified:** with the fix → **2 passed**; on `main` → the reject test **FAILS** (`DID NOT RAISE`).

## Friendly PR title + body
**Title:** Validate the computed chunk_overlap (a float ≥ 1.0 silently drops all content)

**Body:**
> `TokenChunker.__init__` only checks `chunk_overlap >= chunk_size` for `int` inputs. A
> `float` overlap is converted to `int(chunk_overlap * chunk_size)`, which can be ≥
> `chunk_size` while skipping that int-only guard — so the step `chunk_size - chunk_overlap`
> goes ≤ 0, `range()` yields nothing, and `chunk()` returns `[]`: the whole document is
> silently dropped. The docstring already documents `ValueError: If ... chunk_overlap >= chunk_size`.
>
> This validates the computed `self.chunk_overlap` for ints and floats alike. Includes a
> regression test (character tokenizer, no model) that fails on `main` and passes with the
> change, plus a test that a valid fractional overlap still chunks.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check `__init__` still matches current `main` first.)
