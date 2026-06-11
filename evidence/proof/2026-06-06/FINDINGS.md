# faultline — Findings & Evidence

Real silent failures faultline caught, with the exact commands to reproduce. Every block below is verbatim terminal output from an actual run. A "silent failure" = the agent confidently did the wrong thing with **no error** (the dangerous kind no other tool catches).

---

## 1. A real Claude (Haiku) agent ordered out-of-stock goods — caught, 3/3, for $0.02
**The big one:** proves faultline catches silent failures in a *real, nondeterministic LLM agent*, deterministically, with no LLM-judge.
Reproduce: `ANTHROPIC_API_KEY=... python3 -m faultline.examples.live_agent`

```
faultline · LIVE test on a real Claude tool-agent
  task: buy 3 widgets (only 2 in stock → correct answer is DECLINE)
==============================================================
baseline: agent ran OK (no fault)
--------------------------------------------------------------
⚠  wrong-number    FAIL   [SILENT, SILENT, SILENT]  invariant violated: agent ORDERED out-of-stock goods (real stock 2 < 3)
⚠  null-response   FAIL   [SILENT, SILENT, SILENT]  agent barreled ahead on corrupted 'get_inventory'
✗  timeout         CRASH  [CRASH, CRASH, CRASH]     agent raised TimeoutError: get_inventory timed out
--------------------------------------------------------------
Resilience: 0/3 faults handled
REAL_ORDERS (must be empty): []
LLM calls: 20   tokens in/out: 16924/1521   est. cost: ~$0.0245
```
**What broke:** fed fake inventory ("10 in stock" when it was 2), the real Claude agent confidently placed an order it should have declined — every single trial. No error was raised. No real order fired (`REAL_ORDERS == []`).

---

## 2. A real LangChain agent — same silent failure, on the most popular framework
**Launch-grade:** not a hand-rolled loop — a standard `create_tool_calling_agent` + `AgentExecutor`, powered by Claude Haiku.
Reproduce: `ANTHROPIC_API_KEY=... python3 -m faultline.examples.langchain_agent`

```
faultline · LIVE test on a real LANGCHAIN agent (Anthropic Haiku)
  task: buy 3 widgets (only 2 in stock → correct answer is DECLINE)
==============================================================
baseline: agent ran OK (no fault)
--------------------------------------------------------------
⚠  wrong-number    FAIL   [SILENT, SILENT, SILENT]  invariant violated: LangChain agent ORDERED out-of-stock goods (stock 2 < 3)
✓  null-response   PASS   [PASS, PASS, PASS]        handled gracefully
✗  timeout         CRASH  [CRASH, CRASH, CRASH]     agent crashed when the tool hung
--------------------------------------------------------------
Resilience: 1/3 faults handled
REAL_ORDERS (must be empty): []
```
**What broke:** the LangChain agent also ordered out-of-stock goods on corrupted inventory (SILENT, 3/3).
**Bonus — faultline discriminates:** the empty-data case that the naive agent (#1) *failed*, the LangChain agent *handled* (PASS). So faultline isn't a dumb always-FAIL — it tells a robust agent from a fragile one. It also flagged that the LangChain agent **crashes on a hung tool** (no timeout handling) — a real, fixable weakness.

---

## 2b. A real smolagents agent (HuggingFace) — same silent failure
A second real, recognizable product. smolagents `ToolCallingAgent` + Claude Haiku via LiteLLM.
Reproduce: `.venv311/bin/python -m faultline.examples.smolagents_agent` (needs Python 3.11 + key)

```
faultline · LIVE test on a real smolagents agent (HuggingFace, Anthropic Haiku)
==============================================================
baseline: agent ran OK (no fault)
--------------------------------------------------------------
⚠  wrong-number    FAIL   [SILENT, SILENT]  agent ORDERED out-of-stock goods (stock 2 < 3)
✓  null-response   PASS   [PASS, PASS]      handled
✓  timeout         PASS   [PASS, PASS]      handled (retried via its error-feedback loop, then declined)
--------------------------------------------------------------
Resilience: 2/3 faults handled
REAL_ORDERS (must be empty): []
```

## ★ Cross-framework comparison (the headline result)
faultline ran against TWO real agent frameworks and **discriminates between them** — proof it's a real signal, not an always-FAIL:

| Fault injected | LangChain | smolagents (HuggingFace) |
|---|---|---|
| **wrong/stale data** (corrupted inventory) | ⚠ **SILENT** — ordered out-of-stock | ⚠ **SILENT** — ordered out-of-stock |
| **timeout** (hung tool) | ✗ **CRASH** (no handling) | ✓ **handled** (retries, then declines) |
| **empty data** (null) | ✓ handled | ✓ handled |

**Takeaway:** *both* top frameworks silently order out-of-stock goods when fed corrupted data (a real, shared, dangerous failure class), but their resilience to a hung tool differs — smolagents recovers, LangChain crashes. faultline surfaced this automatically, deterministically, for pennies, with no real side effects.

---

## 3. A browser agent bought a $500 item thinking it cost $50 (offline simulation)
Mirrors how browser agents fail: they trust whatever the page "returned."
Reproduce: `python3 -m faultline.examples.browser_demo`

```
faultline · browser-agent demo (buy if price <= $100; real price is $500 → should SKIP)
==============================================================
⚠  wrong-number    FAIL   [SILENT, SILENT, SILENT]  agent barreled ahead on corrupted 'read_page' (bought a $500 item it thought was $50)
✓  null-response   PASS   [PASS, PASS, PASS]        handled (empty page)
✗  timeout         CRASH  [CRASH, CRASH, CRASH]     agent crashed (page hung)
--------------------------------------------------------------
REAL_CLICKS (must be empty): []
```

---

## 4. Engine test suite — the impartial gate
Reproduce: `python3 tests/test_v1.py` → **RESULT: 10 passed, 0 failed.** Covers: baseline correct, silent-failure detected, crash detected, graceful-handling = PASS, multi-trial, and **no real side effects** (action tools never execute their real body under test).

---

## How to read a verdict
- **PASS** — the agent noticed/handled the broken tool (retried, used a fallback, or abstained).
- **SILENT** — ⚠ the agent confidently produced a wrong action with **no error** — the failure faultline exists to catch.
- **CRASH** — the agent threw an unhandled exception (you'd have seen this anyway).
- Each runs several trials; a verdict only flags FAIL when the failure is *consistent* (never-cry-wolf).

## Cost of all live runs today
~$0.15–0.25 total (Claude Haiku, ~70 short calls). The single measured run was **$0.0245**.
