# PR to LlamaIndex (run-llama) — "TreeSummarize: abstain instead of answering from empty context"

**Repo:** https://github.com/run-llama/llama_index  (50k★, active)
**Fork branch (pushed):** https://github.com/run-llama/llama_index/compare/main...aaravanmay:llama_index:abstain-on-empty-chunks
**Status:** STAGED — fork pushed, verified. NOT filed yet (Aarav to review + click "Create PR").

## What it fixes
`TreeSummarize.get_response` / `aget_response`
(`llama-index-core/llama_index/core/response_synthesizers/tree_summarize.py`) repack the
`text_chunks` and, when the repacked result is a single chunk, call the LLM with
`context_str=that chunk`. When `text_chunks` is **empty** (a direct caller) or **every
chunk is blank** (retrieved nodes whose content is empty), `repack` collapses them to
`[""]`, so the LLM is asked to answer with `context_str=""` — it then answers from its
priors, a confident response with no sources.

`BaseSynthesizer.synthesize` already returns `self._empty_response` when `len(nodes) == 0`,
so the *zero-nodes* path is covered. But `get_response` is a **public entry point** in its
own right, and nodes can be **non-empty yet have blank content** — neither is guarded.

## The fix — `tree_summarize.py`
At the top of both `get_response` and `aget_response`, before repacking:

```python
        if not any(chunk and chunk.strip() for chunk in text_chunks):
            return (
                self._empty_response_generator()     # _empty_response_agenerator() in aget_response
                if self._streaming
                else self._empty_response
            )
```

This mirrors `synthesize`'s own streaming/non-streaming empty-response behavior, reusing
the existing `_empty_response` / `_empty_response_generator` hooks.

## The test — `tests/response_synthesizers/test_tree_summarize_empty.py` (in the fork)
Three cases — empty list, all-blank chunks, and the async path — assert the LLM is never
called and the empty response is returned.

**Verified:** with the fix → **3 passed**; on `main` → **3 failed** (the LLM is called with
empty context).

## Friendly PR title + body
**Title:** TreeSummarize: return the empty response instead of querying the LLM with empty context

**Body:**
> `TreeSummarize.get_response`/`aget_response` repack `text_chunks` and call the LLM on the
> single-chunk path. When `text_chunks` is empty (a direct caller) or all chunks are blank
> (retrieved nodes with empty content), repack yields `[""]`, so the LLM is queried with an
> empty `context_str` and answers from its priors.
>
> `synthesize` already guards `len(nodes) == 0`, but `get_response` is also a public entry
> point and nodes can be non-empty yet blank. This adds the same guard at the
> `get_response`/`aget_response` level, reusing the existing `_empty_response` hooks (and
> mirroring `synthesize`'s streaming behavior). Includes a regression test (mocks the LLM)
> that fails on `main` and passes with the change.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check both methods still match current `main` first.)
