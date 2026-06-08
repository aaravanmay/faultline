# faultline

**Silent-failure testing for AI agents.** Everyone tests whether an agent works when everything goes *right*. faultline tests what happens when reality goes *wrong* — a tool returns stale/wrong/empty data, a valid-but-weird input arrives, a model gets upgraded — and catches the moment your agent **confidently does the wrong thing with no error at all.** That's a *silent failure* (a 200-OK-but-wrong), and it's the kind no normal test, eval, or monitor will catch.

It does this **six ways**, all with the **same deterministic detector** — no LLM-judge, so it gates CI without flaking.

![CI](https://github.com/aaravanmay/faultline/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.9%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)

---

### Six ways to provoke a silent failure

The first three feed **honest, valid input** and check the code's own output — so a failure is a *real bug*, never "garbage in, garbage out."

| Mode | What it does | call |
|---|---|---|
| **probe** | feed valid-but-edge inputs and assert a rule that must always hold | `fl.probe` |
| **fuzz** | auto-generate edge inputs and discover the one that breaks it | `fl.fuzz` |
| **scenarios** | run your *agent* through honest, hard real situations and assert a behavioral rule (e.g. "never order more than it has") | `fl.scenarios` |
| **replay** | re-run a recorded trace after a model/prompt/version change, catch silent regressions | `fl.replay` |
| **mine** | watch good runs and let the tool *learn the rules itself*, then enforce them | `fl.mine` |
| **chaos** | break a tool's return on purpose (wrong/stale/empty) to test whether your agent has a *seatbelt* — a resilience test, not a bug-finder | `fl.check` |

One install (`pip install faultline`, pure standard library), one detector. Full walkthrough in **[MODES.md](MODES.md)**.

---

### The live proof — a real agent bug, on honest inputs
`python3 proof_demo.py` runs a real Claude order-agent through honest situations — **every tool returns the true stock, nothing is faked.** The rule: *never order more than the stock it read.* A version with a glue-code bug breaks it; a correctly-written one passes every case (no false alarms):

![faultline catching a real agent bug on honest inputs](evidence/recordings/proof.gif)

```
[A] buggy agent
UNSAFE  one short (wants 3, has 2)   ordered 3 with only 2 in stock (Claude correctly said ship 2, the code ordered 3)
UNSAFE  empty shelf (wants 1, has 0) ordered 1 with only 0 in stock (Claude correctly said ship 0, the code ordered 1)
⚠ 2 honest scenario(s) broke the rule — a real bug, not garbage-in.

[B] safe agent
✓ agent held the rule on every honest scenario.
```

The model answered correctly; the *code* ignored it and shipped what isn't there — the classic silent failure. Watch it: **[evidence/recordings/proof.mp4](evidence/recordings/proof.mp4)**.

---

### Found real bugs in famous AI projects — 6 pull requests open
I pointed faultline's **probe** and **fuzz** modes (honest input → wrong output, never garbage-in) at popular open-source AI projects. Of the bugs found, **10 are unambiguous code defects** (a valid input produces objectively wrong output) and a handful are weaker "should-have-abstained-on-empty" cases. **Six are now open pull requests**, each with a regression test that fails before the fix and passes after:

| Agent | ★ | Silent failure faultline caught | Fix |
|---|---|---|---|
| [Aider](https://github.com/Aider-AI/aider) | 45k | a truncated read silently rewrote a file to half its size (deleted code) | [PR #5236](https://github.com/Aider-AI/aider/pull/5236) |
| [GPT Researcher](https://github.com/assafelovic/gpt-researcher) | 27k | wrote a confident, *cited* report from **empty** retrieval | [PR #1799](https://github.com/assafelovic/gpt-researcher/pull/1799) |
| [LlamaIndex](https://github.com/run-llama/llama_index) | 50k | `TreeSummarize` answered a question from empty context | fix + test ready |
| [gpt-pilot](https://github.com/Pythagora-io/gpt-pilot) | 34k | overwrote a file with empty content (silent data loss) | fix + test ready |
| [STORM](https://github.com/stanford-oval/storm) | 28k | wrote a "sourced" wiki section whose citations point at nothing | fix + test ready |
| [pandas-ai](https://github.com/sinaptik-ai/pandas-ai) | 24k | returned `NaN` from an empty aggregation as a valid number | [PR #1894](https://github.com/sinaptik-ai/pandas-ai/pull/1894) |
| [DB-GPT](https://github.com/eosphoros-ai/DB-GPT) | 19k | labeled a chart with the wrong column on rows containing NULL | fix + test ready |
| [cover-agent](https://github.com/qodo-ai/qodo-cover) | 5k | silently accepted a **stale** coverage report (vs its own docstring) | fix + test ready |
| [chonkie](https://github.com/chonkie-inc/chonkie) | 4k | a float `chunk_overlap` ≥ 1.0 silently dropped the **whole document** | [PR #604](https://github.com/chonkie-inc/chonkie/pull/604) |
| [LlamaIndex](https://github.com/run-llama/llama_index) (#2) | 50k | recency dedup compared the query against the **wrong node's embedding** → dropped the wrong nodes | fix + test ready |
| [llmware](https://github.com/llmware-ai/llmware) | 15k | `expand_text_result_before` never advanced its counter → **duplicated context / infinite loop** | fix + test ready |
| [LangChain](https://github.com/langchain-ai/langchain) | 139k | markdown splitter dropped **everything after an unterminated code fence** | [PR #37964](https://github.com/langchain-ai/langchain/pull/37964) |
| [Agno](https://github.com/agno-agi/agno) | 41k | merged concatenated JSON output → **silently doubled** list fields | fix + test ready |
| [rerankers](https://github.com/AnswerDotAI/rerankers) | 2k | a `None` doc_id survived → id-based score lookups silently returned "not found" | fix + test ready |
| [cognee](https://github.com/topoteretes/cognee) | 18k | emitted a chunk **over** the size limit (oversized word mid-stream), against its own docstring | fix + test ready |
| [OpenInference](https://github.com/Arize-ai/openinference) (Arize) | 1k | a litellm token **count** written to a **cost (USD)** attribute → dashboards show tokens as dollars | [PR #3227](https://github.com/Arize-ai/openinference/pull/3227) |
| [magentic](https://github.com/jackmpcollins/magentic) | 2k | a streamed JSON array with an escaped quote **silently parsed to zero elements** | fix + test ready |

These span real categories — silent data loss, wrong number/column, content dropped, a loop that never advances, a metric written to the wrong (cost) field. The 10 rock-solid ones reproduce on valid input the library should handle; the rest are weaker abstain-on-empty cases. Reproduce one locally with no API key: `python3 examples/demo_silent_rag.py`.

---

## Why
An AI agent calls tools. If a tool returns a *wrong-but-plausible* value, the agent usually has no way to know — it just acts on it. No exception is raised, so your tests pass, your monitors stay green, and your agent quietly ships a bad order, a wrong refund, a deleted record. Most eval and monitoring tools only *measure* the happy path; faultline *injects* these faults on purpose and tells you which ones your agent survives.

```
faultline · check report   (abridged)
==============================================================
baseline: agent ran OK (no fault)
--------------------------------------------------------------
⚠  wrong-number    FAIL   [SILENT, SILENT, SILENT]  invariant violated: ordered out-of-stock goods
✓  null-response   PASS   [PASS, PASS, PASS]        handled — recovered or abstained
✗  timeout         CRASH  [CRASH, CRASH, CRASH]     agent raised TimeoutError
--------------------------------------------------------------
Resilience: 1/3 faults handled
⚠ 1 SILENT failure(s) — the dangerous kind.
Suggested fixes (then re-run to verify): ...
```

## Install
```bash
pip install faultline          # the engine is pure standard library — zero dependencies
```
Try it immediately, no API key needed:
```bash
faultline demo
```

## Quickstart — test *your* agent in 4 steps
The whole integration is: **wrap your tools → write an invariant → run `check`.** Full runnable version: [`faultline/examples/quickstart.py`](faultline/examples/quickstart.py).

```python
import faultline as fl

# 1. wrap each tool faultline is allowed to break
@fl.tool
def get_inventory(item):
    return db.stock(item)

# side effects are CAPTURED, never executed during a test (no real orders, charges, emails)
place_order = fl.wrap(_place_order, is_action=True)

# 2. your agent — any function that takes a task and calls those tools (LLM or not)
def my_agent(task):
    stock = get_inventory(task["item"])
    if stock >= task["qty"]:
        place_order(task["item"], task["qty"])
        return {"decision": "BUY"}
    return {"decision": "DECLINE"}

# 3. an invariant: a rule that must hold no matter what breaks
def must_not_oversell(run):
    out = run["output"]
    if out and out.get("decision") == "BUY":
        return "agent ordered out-of-stock goods"     # return a string => violation

# 4. break the tools and see what survives
result = fl.check(
    my_agent,
    task={"item": "widget", "qty": 3},                # real stock is 2 → correct = DECLINE
    faults=[
        fl.WrongNumber(targets=["get_inventory"]),    # 2 → 10  (the silent killer)
        fl.NullResponse(targets=["get_inventory"]),   # stock comes back empty
        fl.Timeout(),                                  # a tool hangs
    ],
    invariants=[must_not_oversell],
    trials=5,
)
result.report()
```

That's it. Your agent can be a raw loop, a LangChain `AgentExecutor`, a smolagents `ToolCallingAgent`, anything — faultline only needs the tool functions wrapped.

## How it decides PASS / FAIL / CRASH — no LLM-judge, no oracle
faultline runs each fault several times (default 5) and compares against a clean baseline run:

- **PASS** — the agent noticed or absorbed the broken tool: it retried, used a fallback, abstained, or its answer didn't change.
- **FAIL (silent)** — ⚠ the agent confidently changed its answer on corrupted data, with no retry and no sign of uncertainty — **or it broke an invariant you defined.** This is the failure faultline exists to catch.
- **CRASH** — the agent threw an unhandled exception (you'd have seen this in prod anyway).

A fault is only reported as FAIL when the failure is **consistent across trials**, so it never cries wolf on a fluke. **Invariants are the reliable signal — define what "bad" means for your agent.** (The built-in "answer silently changed" heuristic is a zero-config bonus; it's most accurate when your agent returns a canonical answer rather than incidental free text.)

## The fault library
| Fault | What it does | Catches |
|---|---|---|
| `WrongNumber(factor=5)` | returns a plausible wrong number | stale caches, unit bugs, bad fields — **the silent killer** |
| `StaleData` | returns the first value forever (cache never refreshes) | agents that don't notice frozen data |
| `Truncate` | returns only half a list/string | "I saw 3 of 10 results and thought that was all" |
| `NullResponse` | returns `None` | agents that guess instead of abstaining |
| `Timeout` | the tool hangs / raises | missing timeout & retry handling |
| `ServerError(code=500)` | the tool returns an HTTP error | missing error handling |

Point any fault at specific tools with `targets=["get_inventory"]`, or leave it off to hit every tool.

## Reusable invariants (`faultline.invariants`)
You can write any `inv(run) -> str | None` rule, but the most common silent failures are already codified as **deterministic, reusable invariants** — distilled from the real bugs above. Drop them into any `check(...)`:

| Invariant | Catches | Distilled from |
|---|---|---|
| `numeric_answer_finite()` | a `NaN`/`inf` returned as a real number | pandas-ai |
| `abstain_when_context_empty(tools=[...])` | a confident answer built from empty retrieval | GPT Researcher · STORM · LlamaIndex |
| `no_poison_parroting(targets=[...])` | a corrupted tool value echoed verbatim into the answer | `WrongNumber` · `StaleData` |
| `no_silent_shrink(read_tools=[...], write_tools=[...])` | a write that drops most of an existing file | Aider · gpt-pilot |

```python
import faultline as fl
res = fl.check(my_rag_agent, task="…",
               faults=[fl.NullResponse(targets=["search"])],
               invariants=[fl.abstain_when_context_empty(tools=["search"])])
```

They're **deterministic** — same verdict every run — which is exactly what makes a silent-wrong gate-able in CI (no flaky LLM-judge).

## Run it in CI (fail the PR on a silent failure)
Add a `faultline_suite.py` to your repo:
```python
import faultline as fl
from my_app import my_agent, must_not_oversell

def faultline_suite():
    return {
        "agent": my_agent,
        "task": {"item": "widget", "qty": 3},
        "faults": [fl.WrongNumber(targets=["get_inventory"]), fl.Timeout()],
        "invariants": [must_not_oversell],
    }
```
Then either run `faultline run faultline_suite.py` (exits non-zero on any silent failure or crash), or use the GitHub Action:
```yaml
# .github/workflows/faultline.yml
name: faultline
on: [pull_request]
jobs:
  chaos:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: aaravanmay/faultline@main
        with:
          suite: faultline_suite.py
```

## What this is / isn't
- **Is:** a reliability tool for the people *building* AI agents — break the tools, find the silent failures, gate them in CI. Runs entirely in your own environment; it never sees your data.
- **Isn't:** a security/jailbreak red-teamer (different problem, crowded space), and not an eval framework that only *measures* quality. faultline *injects* failures. It complements your evals; it doesn't replace them.

## Status
Alpha. The engine + invariant library are built and tested (core 8/8, invariants 16/16), and proven by finding **17 real silent bugs in 16 popular open-source agents** (see the table above + [`evidence/wild_catches/`](evidence/wild_catches/)). Works on Python 3.9–3.12. API may still change before 1.0.

## License
MIT © 2026 Aarav Goenka
