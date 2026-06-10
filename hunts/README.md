# Hunts — silent failures faultline caught in real, popular open-source agents

Each hunt points faultline at a real installed library, injects a realistic fault, and records
what happened — verbatim, including the ones where the library was fine.

**Honesty labels (never blurred):**
- **CATCH (PR filed)** — a real upstream bug; a fix PR is open, linked, and its state is current.
- **CATCH (PR closed)** — filed, then closed (e.g. by a repo bot). Still disclosed as closed.
- **DEMONSTRATION** — faultline's invariant fires on real library code for a *known* risk the library
  doesn't claim to guard (e.g. "a RAG pipeline answers from empty context"). Real code, not a fileable bug.
- **NO-CATCH** — the library handled the fault correctly. Published on purpose: these are credibility deposits.

| # | Target | Label | One line |
|---|---|---|---|
| 01 | chonkie (4k★) | CATCH · [PR #604](https://github.com/chonkie-inc/chonkie/pull/604) (open) | a float overlap ≥1.0 silently dropped the whole document |
| 02 | pandas-ai (24k★) | CATCH · [PR #1894](https://github.com/sinaptik-ai/pandas-ai/pull/1894) (open) | NaN returned as a valid numeric answer |
| 03 | GPT-Researcher (27k★) | CATCH · [PR #1799](https://github.com/assafelovic/gpt-researcher/pull/1799) (open) | fabricated a full report when every source came back empty |
| 04 | Aider (45k★) | CATCH · [PR #5236](https://github.com/Aider-AI/aider/pull/5236) (open) | a truncated read rewrote a file missing its bottom half |
| 05 | Haystack (22k★) | DEMONSTRATION | a RAG pipeline builds a "grounded" prompt from zero documents |

Reproduce any of these: `pip install faultline <target>` then run the hunt script. Cost per hunt: a few cents.
