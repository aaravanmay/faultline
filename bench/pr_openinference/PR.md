# PR to OpenInference (Arize-ai) — "litellm: completion text_tokens written to a COST attribute, not a token-count"

**Repo:** https://github.com/Arize-ai/openinference  (1k★, active — pushed 2026-06-08)
**Fork branch (pushed):** https://github.com/Arize-ai/openinference/compare/main...aaravanmay:openinference:fix-completion-text-tokens-cost-attr
**Status:** FILED — PR #3227 (open).

## What it fixes
In `_set_token_counts_from_usage`
(`python/instrumentation/openinference-instrumentation-litellm/.../litellm/__init__.py`), the
completion-side `text_tokens` (a token **count**) is written to a **cost** attribute:

```python
text_tokens = _get_value(completion_tokens_details, "text_tokens")
if text_tokens is not None:
    _set_span_attribute(
        span, SpanAttributes.LLM_COST_COMPLETION_DETAILS_OUTPUT, text_tokens   # <-- llm.cost.* (USD)
    )
```

`LLM_COST_COMPLETION_DETAILS_OUTPUT` is `"llm.cost.completion_details.output"` — a
**dollar-denominated cost** field (the semconv docstring says *"All values should be in USD"*).
Every sibling in this function writes counts to `llm.token_count.*` (e.g. the completion
`reasoning_tokens`/`audio_tokens` and the parallel prompt-side `text_tokens`). Only this branch
lands in the cost namespace — a copy-paste slip.

**Effect:** any litellm call against a model that returns `completion_tokens_details.text_tokens`
(multimodal / audio OpenAI models populate it) emits a span where a **token count sits under a
cost attribute** — so a cost dashboard reads e.g. **`$500`** for 500 text tokens. No exception;
the span is emitted "successfully." It's the only write to that attribute, so nothing masks it.

## The fix (one monorepo, 3 source lines + a test)
1. **semconv** — add the missing symmetric constant (mirrors `_AUDIO` / `_REASONING`):
   `LLM_TOKEN_COUNT_COMPLETION_DETAILS_TEXT = "llm.token_count.completion_details.text"`
2. **semconv test** — add `"text": ...COMPLETION_DETAILS_TEXT` to the `completion_details` mapping
   (keeps `test_nesting` green).
3. **litellm instrumentation** — route the count to the new token-count constant instead of the
   cost one.

## The test — `.../litellm/tests/test_completion_text_tokens_not_cost.py` (in the fork)
A fake span + a stub usage object (`completion_tokens_details.text_tokens = 500`); asserts the
value is **not** under `LLM_COST_COMPLETION_DETAILS_OUTPUT` and **is** under the token-count
attribute. No live LLM (only opentelemetry + semconv).

**Verified:** with the fix → litellm test **PASS** and the semconv `test_nesting` **green (10/10)**;
on `main` → litellm test **FAIL** (count under the cost attribute).

## Friendly PR title + body
**Title:** litellm: record completion text_tokens as a token count, not a cost (USD) attribute

**Body:**
> `_set_token_counts_from_usage` writes the completion `text_tokens` count into
> `LLM_COST_COMPLETION_DETAILS_OUTPUT` (`llm.cost.completion_details.output`, a USD field), while
> every sibling uses `llm.token_count.*`. So a model returning `completion_tokens_details.text_tokens`
> produces a span where a token count shows up as a dollar cost (e.g. a cost panel reads $500 for
> 500 tokens), with no error.
>
> This adds a symmetric `LLM_TOKEN_COUNT_COMPLETION_DETAILS_TEXT` semconv constant (mirroring
> `_AUDIO`/`_REASONING`) and routes the count there. Includes a regression test that fails on
> `main` and passes with the change; the semconv nesting test stays green. Happy to rename the
> constant if you'd prefer a different convention.

## To file (≈30 sec)
1. Open the compare URL → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check the function + semconv still match current `main` first.)
