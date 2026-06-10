# Hunt 03 — GPT-Researcher fabricated a full report from zero sources

**Target:** [GPT-Researcher](https://github.com/assafelovic/gpt-researcher) (27k★, autonomous research agent)
**Label:** CATCH — [PR #1799](https://github.com/assafelovic/gpt-researcher/pull/1799) (open)

## The setup
GPT-Researcher scrapes a set of web sources, then writes a report from what it gathered. I armed
faultline so that every page it scraped came back **empty** — the realistic case of a blocked
site, a rate limit, or a network hiccup where the fetch returns 200 but no content.

## What happened
Given nothing to work with, the agent didn't abstain or warn. It wrote a **13,000-character,
fully confident report** — "The Eiffel Tower was completed on March 31, 1889..." — complete with
a specifications table, a workforce headcount, and a **References section citing books and
archives that it never read** (it had read nothing). Zero uncertainty, no error, no signal
anywhere that it was working from empty sources.

It happens to be right about the Eiffel Tower because the model already knew the answer — which
is the trap. The report *looks* researched. On any topic the model is wrong or stale about, the
same path produces a confident, sourced-looking, fabricated report.

## The fix
Abstain (or clearly flag low confidence) when no content was gathered, instead of generating a
report from nothing. Test fails before the fix, passes after.

## Why it matters
The entire value proposition of a research agent is that its output is grounded in sources. A
silent path that fabricates a citation-laden report from zero sources breaks that promise
invisibly — the reader has no way to tell this report apart from a real one.
