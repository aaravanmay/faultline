# faultline — launch post drafts

Honest, proof-first. The strength is *we already caught real silent bugs in famous agents*,
not polish. Do not claim partnership/endorsement from any project.

---

## Show HN (title + body)

**Title:** Show HN: faultline – break an AI agent's tools to find where it silently lies

**Body:**

Most AI agents don't fail by crashing. They fail *silently*: a tool returns stale, wrong,
truncated, or empty data, and the agent gives you a confident, well-formatted, WRONG answer
with a 200 OK. Evals on clean data pass it. An LLM-judge often passes it too. Then it does
the wrong thing in production.

faultline is chaos engineering for that. You wrap your agent's tools, and it re-runs the
agent while deliberately breaking each tool — wrong numbers, stale data, truncation, empty
results, timeouts, 500s. It flags the dangerous case: the agent changed its answer based on
corrupted data, with no error and no uncertainty (we call it SILENT-WRONG).

The detection is deterministic, not an LLM-judge: fault-specific behavioral invariants
(e.g. "if all retrieval came back empty, the answer must abstain"). Same verdict every run,
so it's CI-able.

To prove it's not a toy, I pointed it at popular open-source agents and it found real silent
failures — and I filed/staged the fixes:

- **Aider** (whole-file edit) silently rewrote a file to a fraction of its size on a
  truncated read → PR (no-shrink guard).
- **GPT Researcher** wrote a confident, "cited" report from empty retrieval → PR #1799.
- **pandas-ai** returned `NaN` from an aggregation over empty data as a valid number → PR.
- **DB-GPT** labeled chart points with the wrong column on NULL rows → PR.
- **LlamaIndex** (TreeSummarize) answered from empty context → PR.
- **STORM** wrote a sourced Wikipedia section from no sources → PR.

30-second demo (no keys): `python3 examples/demo_silent_rag.py` — it reproduces the
empty-context fabrication and catches it.

I'm 15 and building this in the open. It's early — the core engine + fault library + the
invariant library are there; adapters for LangGraph/OpenAI/Anthropic tool-calling are next.
I'd love feedback on the detection model: what silent failure modes should it catch that it
doesn't yet?

Repo: <link>   Demo clip: <link>

---

## One-paragraph version (for X / LinkedIn / DMs)

AI agents rarely crash — they fail silently: a broken tool returns wrong/empty data and the
agent answers confidently and wrong, 200 OK. I built **faultline** to break an agent's tools
on purpose and catch exactly that, with deterministic invariants (not an LLM-judge) so it
runs in CI. To prove it works I ran it against famous open-source agents and found real
silent bugs in Aider, GPT Researcher, pandas-ai, DB-GPT, LlamaIndex and STORM — and filed
the fixes. Open source, demo runs in 30s with no keys. Building in the open at 15.

---

## Notes for posting
- Lead with the Aider / GPT Researcher catches — most HN readers use those.
- Have the demo clip + repo link ready *before* posting; reply fast in the first hour.
- If a maintainer comments, be gracious + specific; never imply they endorse faultline.
- Title A/B options:
  - "Show HN: faultline – chaos engineering for AI agents (found real silent bugs in 6 of them)"
  - "Show HN: faultline – break your agent's tools to find where it confidently lies"
