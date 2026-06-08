# PR to GPT Researcher — "Don't fabricate a report when no research content was gathered"

**Repo:** https://github.com/assafelovic/gpt-researcher
**What it fixes:** `ReportGenerator.write_report` passes the gathered context straight
to the report LLM with no check that anything was actually retrieved. So when *every*
source returns empty (searches rate-limited, blocked, or genuinely no hits), it writes
a confident, fully-sourced-looking report from the model's priors — it even invents
citations. faultline reproduced this: with all scraped content emptied, it produced a
**13,000-char report with a fabricated References section and zero uncertainty.**

Verified: the test below FAILS on current `main` and PASSES with the fix (it mocks the
report LLM, so it needs no API call).

---

## 1) The fix — `gpt_researcher/skills/writer.py`, in `ReportGenerator.write_report`

Right after `context = ext_context or self.researcher.context`, add:

```python
        # Guard against fabricating a report from nothing: if no research content was
        # gathered (every retriever returned empty / was blocked / rate-limited), don't
        # silently write a confident, sourced-looking report - abstain so it is visible.
        _ctx = "\n".join(context) if isinstance(context, list) else str(context or "")
        if not _ctx.strip():
            return (
                f'I could not gather any source material for "{self.researcher.query}". '
                "No sources were retrieved (searches may have returned nothing or been "
                "blocked), so I am not able to produce a reliable, sourced report."
            )
```

(Optional, if you prefer it opt-out: gate on a `self.researcher.cfg` flag and/or emit a
`stream_output("logs", "no_context", ...)` warning before returning.)

## 2) The test — `bench/pr_gpt_researcher/test_no_fabrication.py` in this repo
Drop it into gpt-researcher's suite (e.g. `tests/report/test_empty_context.py`).

## 3) Friendly PR title + body

**Title:** Don't fabricate a report when no research content was gathered

**Body:**
> While testing how GPT Researcher handles empty retrievals, I found it produces a
> confident, fully-sourced-looking report (with invented citations) when *every* source
> returns no content — searches rate-limited, blocked, or genuinely empty.
> `ReportGenerator.write_report` passes the (empty) context straight to the report LLM
> with no check, so the model fills in from its priors.
>
> This adds a guard: if no research content was gathered, abstain with a clear message
> instead of writing. Includes a regression test (mocks the report LLM, no API call) that
> fails on `main` and passes with the change. Happy to make it a config flag if you'd
> rather keep the current behavior opt-in.

---

## How to file it (same as the Aider one)
1. Fork **github.com/assafelovic/gpt-researcher**, `git clone` your fork, `cd` in.
2. `git checkout -b abstain-on-empty-context`
3. Apply the fix in `gpt_researcher/skills/writer.py`; copy the test to `tests/`.
4. Run it: `python -m pytest tests/<the test>.py` → should pass.
5. `git commit`, `git push origin abstain-on-empty-context`, then GitHub's
   **"Compare & pull request"** → paste the body → submit.
6. Re-check `write_report` matches current `main` first (repos drift).
