# PR to llmware (llmware-ai) — "Decrement block_id in expand_text_result_before so it walks backwards"

**Repo:** https://github.com/llmware-ai/llmware  (14.8k★, active — pushed 2026-05-17)
**Fork branch (pushed):** https://github.com/llmware-ai/llmware/compare/main...aaravanmay:llmware:fix-expand-before-missing-decrement
**Status:** STAGED — fork pushed, verified, clean diff (2 lines/file). NOT filed yet (Aarav to review + click "Create PR").

## What it fixes
`Query.expand_text_result_before` (`llmware/retrieval.py`) — and its duplicate
`Library.expand_text_result_before` (`llmware/library.py`) — expand a retrieved block with
the preceding context window. The loop:

```python
block_id = block["block_ID"] - 1
...
while len(before_text) < window_size and block_id >= 0:
    before_block = self.block_lookup(block_id, doc_id)
    if before_block:
        before_text += before_block["text"]
        pre_blocks.append(before_block)
    # block_id is NEVER decremented
```

`block_id` never changes inside the loop, so it re-looks-up the **same** preceding block every
iteration:
- **Duplicated context:** if that block is shorter than `window_size` (400 by default — most
  are), its text is appended over and over until the window fills, returning the same paragraph
  repeated N times as the "expanded context."
- **Infinite hang:** if that `block_lookup` returns `None` (block missing, `block_id >= 0`),
  `before_text` stays `""` and the loop never terminates — no exception.

The sibling `expand_text_result_after` does `block_id += 1` correctly, so this is clearly an
omitted decrement, not intended behavior.

## The fix — `retrieval.py` + `library.py`
Add the decrement inside the loop, mirroring `expand_text_result_after`:

```python
        if before_block:
            before_text += before_block["text"]
            pre_blocks.append(before_block)

    block_id -= 1  # Decrement block_id for next iteration (mirrors expand_text_result_after)
```

(2 lines in each of the two files — the method is duplicated across `Query` and `Library`.)

## The test — `tests/test_expand_before_decrement.py` (in the fork)
Calls the method via the unbound method with a stub `self` (only `block_lookup` is used — no
DB/account/LLM); the stub raises after 200 calls so a regression can't hang CI. Asserts the
lookups walk `[4, 3, 2, 1, 0]` and the results are the distinct preceding blocks.

**Verified:** with the fix → **PASS**; on `main` → **FAIL** (re-looks-up the same block).

## Friendly PR title + body
**Title:** Fix `expand_text_result_before` never advancing block_id (duplicated context / infinite loop)

**Body:**
> `expand_text_result_before` (in both `retrieval.py` and `library.py`) never decrements
> `block_id` in its loop, so it re-looks-up the same preceding block every iteration: it either
> returns the same block's text repeated until `window_size` (duplicated context) or loops
> forever if that block lookup returns `None`. The sibling `expand_text_result_after` increments
> `block_id` correctly; this mirrors it with a decrement.
>
> Includes a regression test (stub `block_lookup`, no DB/LLM; bounded so it can't hang CI) that
> fails on `main` and passes with the change.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check both copies still match current `main` first.)
