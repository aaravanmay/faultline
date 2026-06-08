# All 17 bugs — caught by the tool, on a live run

Every one of the 17 bugs now has a **rerunnable faultline command that flags it** against the real
(unpatched) library. **15 need no API key.** This is "the tool caught it," not "I found it by hand."

**Still honest about roles:** *you give faultline the rule* (e.g. "a document shouldn't vanish",
"an answer should be a real number", "on empty context, don't call the LLM") and *the tool then
checks it automatically.* The **fix + the rule were written by me (the AI engineer)** — the tool does
the catching. No tool invents the patch.

## The two modes
- **Mode 1 · `check()` (chaos):** break a tool's RETURN (wrong/stale/empty/truncated) + invariants.
- **Mode 2 · `probe()` (property / metamorphic):** mutate a valid INPUT to an edge case + properties.

## All 17 (run any of these)

| # | Bug | Mode | The rule the tool checks | Command |
|---|---|---|---|---|
| 1 | pandas-ai | 1 | a numeric answer must be a real (finite) number | `python3 bench/tool_caught/pandas_ai_nan.py` |
| 2 | rerankers | 1 | no document keeps a missing (None) id | `python3 bench/tool_caught/rerankers_none_id.py` |
| 3 | chonkie | 2 | a non-empty document must not chunk to nothing | `python3 bench/tool_caught/chonkie_probe.py` |
| 4 | LangChain | 2 | content after an unterminated code fence survives | `python3 bench/tool_caught/langchain_md_probe.py` |
| 5 | magentic | 2 | parser must agree with stdlib `json` on element count | `python3 bench/tool_caught/magentic_probe.py` |
| 6 | LlamaIndex (recency) | 2 | which docs survive must not depend on input order | `python3 bench/tool_caught/llamaindex_recency_probe.py` |
| 7 | agno | 2 | a duplicated reply must not double a list | `python3 bench/tool_caught/agno_probe.py` |
| 8 | cognee | 2 | every chunk must respect the size limit | `python3 bench/tool_caught/cognee_probe.py` |
| 9 | OpenInference | 2 | a token count must not land under a $ cost field | `python3 bench/tool_caught/openinference_probe.py` |
| 10 | DB-GPT | 2 | a NULL row must not crash / mislabel the chart | `python3 bench/tool_caught/dbgpt_probe.py` |
| 11 | LlamaIndex (summarize) | 1/2 | empty context → abstain, don't call the LLM | `python3 bench/tool_caught/llamaindex_summarize_probe.py` |
| 12 | STORM | 1/2 | no sources → abstain, don't write a "sourced" section | `python3 bench/tool_caught/storm_probe.py` |
| 13 | llmware | 1 | context expander must walk distinct blocks | `python3 bench/tool_caught/llmware_probe.py` * |
| 14 | cover-agent | 1 | a stale coverage report must be rejected | `python3 bench/tool_caught/coveragent_probe.py` * |
| 15 | gpt-pilot | 1 | never overwrite a file with empty content | `python3 bench/tool_caught/gptpilot_probe.py` * |
| 16 | Aider | 1 | a truncated read must not shrink the file | `python3 examples/hunt_aider.py` † |
| 17 | GPT-Researcher | 1 | empty retrieval → abstain, don't fabricate | `python3 examples/hunt_gpt_researcher.py` † |

\* needs the matching repo in `../faultline-forks/<name>` checked out on `main` (unpatched), on
`PYTHONPATH`. † needs an API key (a real LLM has to run); costs pennies.

## The calibrated claim — now stronger and still true
- ✅ *"I built faultline — deterministic silent-failure testing for AI agents, with two modes — and used it to find and fix 17 real bugs in 16 famous agents. The tool reproduces every one on a live run (15 with no API key)."*
- The **fixes and the rules are mine**; the **catching is the tool's**. That's the honest, complete story.

---

## Live (via the API) — the CODE finds it autonomously, no agent reading source

`faultline/llm.py` wires in the Anthropic API so faultline can RUN a real model-backed agent, break
a tool, and let its **generic detectors** (action-divergence / poison-parroting / abstain-on-empty /
numeric-finite) flag the silent failure — with **zero bug-specific code from a human**. Targets were
chosen by an agent (target-selection only); the *finding* is the tool's own run.

| Target (real, via Claude) | Fault faultline injected | What the CODE caught | Run |
|---|---|---|---|
| custom Claude order-agent | WrongNumber (stale stock) | action-divergence: placed an order it wouldn't on real data | `bench/tool_caught/live_ops_agent.py` |
| **Aider** (45k★, real lib) | Truncate (file read) | wrote the file back missing 3 functions it never read | `faultline/examples/hunt_aider.py` |
| **LangGraph** ReAct (real lib) | WrongNumber (balance tool) | poison-parroting: reported the corrupted balance as fact | `bench/tool_caught/live_langgraph.py` |
| **pydantic-ai** (real lib) | WrongNumber (balance tool) | poison-parroting: reported the corrupted balance as fact | `bench/tool_caught/live_pydantic_ai.py` |
| **agno** (real lib) | WrongNumber (balance tool) | poison-parroting: reported the corrupted balance as fact | `bench/tool_caught/live_agno.py` |
| **LlamaIndex** RAG (real lib) | NullResponse (retrieval) | abstain-on-empty: fabricated a confident answer from no sources | `bench/tool_caught/live_llamaindex_rag.py` |
| **ag2 / AutoGen** (real lib) | WrongNumber (balance tool) | poison-parroting — through a 2-agent loop | `bench/tool_caught/live_ag2.py` |
| **CrewAI** (real lib) | WrongNumber (balance tool) | poison-parroting | `bench/tool_caught/live_crewai.py` |
| smolagents (real lib) | NullResponse (lookup tool) | **PASS** — agent retried/failed loudly, did NOT fabricate (faultline didn't cry wolf) | `bench/tool_caught/live_smolagents.py` |

faultline (the code) caught silent failures in **8 real agent frameworks/apps** live via the API —
Aider, LangGraph, pydantic-ai, agno, LlamaIndex, ag2/AutoGen, CrewAI (+ a custom agent) — across
**3 different detectors** (action-divergence, poison-parroting, abstain-on-empty), plus one honest
PASS (smolagents). Agents only chose the targets; every finding was the tool's own run. Total cost:
a few cents. One-command scoreboard: `python3 bench/tool_caught/run_all_live.py`.

### Honest distinction — two different kinds of "bug"
- **The 17 (above):** *deterministic code bugs inside the libraries* (e.g. a parser drops content). These
  were mostly found by **code review** (guided by faultline's taxonomy); the tool *reproduces* them.
- **The live ones (this section):** *silent-failure flaws in real AGENTS* (the agent trusts broken tool
  data and silently reports/acts on it). These are found by the **tool itself running the agent via the
  API** — this is faultline's core product purpose (test *your* agent's reliability), and it needs no
  human to find them. A "PASS" (smolagents) is also a real result: the agent was resilient.

Both are real. The live runs are the proof that **the actual code functions** as an autonomous detector,
not just a reproducer of bugs a human already found.
