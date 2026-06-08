# PR to cognee (topoteretes) — "chunk_by_sentence: raise on an oversized word mid-stream, not only at the end"

**Repo:** https://github.com/topoteretes/cognee  (17.7k★, active — pushed 2026-06-07)
**Fork branch (pushed):** https://github.com/topoteretes/cognee/compare/main...aaravanmay:cognee:raise-on-oversized-word-midstream
**Status:** STAGED — fork pushed, verified. NOT filed yet (Aarav to review + click "Create PR").

## What it fixes
`chunk_by_sentence` (`cognee/tasks/chunks/chunk_by_sentence.py`) — its docstring states it
*"ensures that sentences do not exceed this length, raising a ValueError if an individual word
surpasses it."* The **trailing-sentence** path enforces that:

```python
if len(sentence) > 0:
    if maximum_size and sentence_size > maximum_size:
        raise ValueError(f"Input word {word} longer than chunking size {maximum_size}.")
```

But the **main loop** does not:

```python
if maximum_size and (sentence_size + word_size > maximum_size):
    cut_type = "sentence_cut" if word_type_state == "word" else word_type_state
    yield (paragraph_id, sentence, sentence_size, cut_type)   # may yield an over-budget chunk
    sentence = word
    sentence_size = word_size            # word_size itself may exceed maximum_size — unchecked
```

So a single token longer than `maximum_size` (a long URL, a code identifier, a base64 blob, CJK
text under token-counting) appearing **anywhere except the last position** is **silently emitted
as a chunk whose size exceeds `maximum_size`**, which then flows through `chunk_by_paragraph` into
embeddings/storage with no error. The exact same token raises `ValueError` only if it happens to
land last — a silent-vs-loud asymmetry that violates the function's own documented contract.

Verified (size = char length): `chunk_by_sentence("hi supercalifragilistic ok done", maximum_size=5)`
yields chunk sizes `[3, 21, 3, 4]` on `main` (the `21` is silently over budget); the same word
placed last raises `ValueError`.

## The fix — `chunk_by_sentence.py`
Add the same guard the tail path has, into the main loop:

```python
if maximum_size and (sentence_size + word_size > maximum_size):
    if word_size > maximum_size:
        raise ValueError(f"Input word {word} longer than chunking size {maximum_size}.")
    cut_type = ...
```

## The test — `cognee/tests/unit/processing/chunks/test_chunk_by_sentence_oversized.py` (in the fork)
Stubs `get_word_size` (size = char length, so no embedding engine / LLM), feeds an oversized word
mid-stream, asserts `ValueError` is raised.

**Verified:** with the fix → **raises (PASS)**; on `main` → **no raise**, yields a size-21 chunk
(verified by loading the function in isolation with the embeddings import stubbed).

## Friendly PR title + body
**Title:** chunk_by_sentence: enforce maximum_size for an oversized word mid-stream (not only at the end)

**Body:**
> `chunk_by_sentence`'s docstring says it raises `ValueError` when an individual word exceeds
> `maximum_size`. The trailing-sentence path does, but the main loop silently yields an
> over-budget chunk when the oversized token isn't last — so a long URL/identifier/base64/CJK
> token mid-document produces a chunk larger than `maximum_size` that flows into embeddings with
> no error. This adds the same guard to the main loop. Includes a regression test (stubs
> `get_word_size`, no LLM) that fails on `main` and passes with the change.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check the loop still matches current `main` first.)
