# PR to STORM (stanford-oval) — "Abstain when a section has no retrieved information"

**Repo:** https://github.com/stanford-oval/storm  (28k★, active)
**Fork branch (pushed):** https://github.com/stanford-oval/storm/compare/main...aaravanmay:storm:abstain-on-empty-section
**Status:** STAGED — fork pushed, verified. NOT filed yet (Aarav to review + click "Create PR").

## What it fixes
`ConvToSection.forward` (in `knowledge_storm/storm_wiki/modules/article_generation.py`)
builds `info` by joining the snippets in `collected_info`. When that list is **empty**
— a cold-start topic, a niche section the retriever found no hits for, or an empty
knowledge base — `info` stays `""` and is passed straight to the section-writing LLM.
The model then writes a confident, "sourced" Wikipedia section with citation markers
like `[1][3]` that point at **no sources**, and STORM merges it into the published
article. No warning, no error — a textbook silent-wrong.

The co-storm path already guards this exact case (`AnswerQuestionModule.forward` returns
an "insufficient information" abstention). The storm-wiki writer simply never got the
same guard — so this is a clear, low-risk oversight fix, not a behavior debate.

## The fix — `knowledge_storm/storm_wiki/modules/article_generation.py`
Right after the `for ... collected_info` loop builds `info`, before the word-count trim:

```python
        # Don't fabricate a section from nothing: if no information was retrieved for this
        # section (empty knowledge base / no hits), abstain instead of asking the LLM to write
        # a sourced section with citation markers ([1], [2], ...) pointing at no sources.
        if not info.strip():
            return dspy.Prediction(section="")
```

The caller assembles sections into the article; an empty section is dropped/handled
cleanly, which is strictly safer than a fabricated one.

## The test — `tests/test_conv_to_section_empty.py` (in the fork)
Mocks `write_section`, calls `forward(..., collected_info=[])`, asserts the section LLM
is **never called** and the result is empty. No API call.

**Verified:** `PYTHONPATH=<fork> pytest tests/test_conv_to_section_empty.py`
→ **PASS** with the fix, **FAIL** on `main` (it calls the LLM to write from empty info).

## Friendly PR title + body
**Title:** Abstain when a section has no retrieved information (don't fabricate a sourced section)

**Body:**
> While testing how STORM handles empty retrieval, I found `ConvToSection.forward` will
> write a full Wikipedia section — with citation markers `[1][2]` pointing at nothing —
> when `collected_info` is empty (cold-start topic, a section with no web hits, or an
> empty knowledge base). The empty `info` string is passed straight to the section LLM
> with no guard, and the fabricated section is merged into the article.
>
> The co-storm `AnswerQuestionModule.forward` already handles this with an
> "insufficient information" abstention; the storm-wiki writer doesn't. This ports the
> same guard: if no information was gathered, return an empty section instead of
> fabricating one. Includes a regression test (mocks the section LLM, no API call) that
> fails on `main` and passes with the change. Happy to return a placeholder string
> instead of an empty section if you prefer.

## To file (≈30 sec)
1. Open the compare URL above → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check `forward` still matches current `main` first — repos drift.)
