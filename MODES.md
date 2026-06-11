# The six modes

faultline provokes a silent failure six different ways. Every mode reports the same way and uses the
**same deterministic detector** (no LLM-judge), so any of them can gate CI without flaking.

A *silent failure* = your agent confidently does the wrong thing and **raises no error** — the 200-OK-but-wrong
that your tests pass, your evals miss, and your monitors stay green for.

```bash
pip install -e .          # pure standard library, no dependencies for the core
```

```python
import faultline as fl
```

| Mode | The question it answers | When to reach for it |
|---|---|---|
| [probe](#1-probe--assert-a-rule-on-edge-inputs) | "On a valid-but-weird input, does my rule still hold?" | functions with a known invariant |
| [fuzz](#2-fuzz--find-the-breaking-input-for-me) | "Is there *any* input that breaks this? Find it." | you don't know the edge case yet |
| [scenarios](#3-scenarios--test-the-agent-on-honest-hard-cases) | "On honest, hard real situations, does my agent break a rule?" | agents that take actions (no garbage-in) |
| [replay](#4-replay--catch-a-regression-after-a-change) | "I changed the model/prompt — did behavior silently drift?" | upgrades, refactors, dep bumps |
| [mine](#5-mine--let-the-tool-learn-the-rules-itself) | "What rules *should* hold? Learn them from good runs." | you can't enumerate the rules by hand |
| [chaos](#6-chaos--break-its-tools-resilience-test) | "If a tool *lies* to my agent, does it have a seatbelt?" | resilience test (prone to garbage-in — see note) |

---

## 1. probe — assert a rule on edge inputs

You hand faultline a few valid-but-edge inputs and a rule. It runs each input and flags any that break the
rule silently (no crash, wrong answer).

```python
def chunk(overlap):
    return [] if (isinstance(overlap, float) and overlap >= 1) else ["a", "b"]

def nonempty(inp, out, err):           # the rule: chunking must never silently produce nothing
    if err is None and not out:
        return "silently produced 0 chunks"

fl.probe(
    chunk,
    fl.mutations(0, ("fractional>=1", lambda base: 1.5)),   # edge input: overlap = 1.5
    [nonempty],
).report()
# catches: overlap 1.5 -> [] -> "silently produced 0 chunks"
```

---

## 2. fuzz — find the breaking input for me

Same idea as probe, but you don't supply the edge cases — faultline generates them from the base input's
type (strings, numbers, lists) and finds the one that breaks your rule.

```python
fl.fuzz(chunk, base=0, properties=[nonempty]).report()
# tried 37 auto-generated inputs, found 1 breaker: fractional-1.5
```

This is exactly how faultline auto-discovered a real bug in [chonkie](https://github.com/chonkie-inc/chonkie):
a fractional overlap ≥ 1.0 silently dropped the whole document.

---

## 3. scenarios — test the agent on honest hard cases

probe/fuzz test a *function*. `scenarios` tests your **agent** — but the honest way. You give it a battery
of *real, legal* situations (no faked tool data) and one behavioral rule. A failure is a genuine agent bug,
not "garbage in, garbage out": every tool returns the truth, so if the agent still does something unsafe,
that's on the agent.

```python
WORLD = {"a": 3, "b": 2, "c": 0}            # the TRUTH — nothing is faked

@fl.tool
def get_inventory(item): return WORLD[item]
place_order = fl.wrap(_place_order, is_action=True)

def agent(task):                            # a real (or LLM-backed) order agent
    stock = get_inventory(task["item"])
    ...

def never_oversell(run):                    # the rule, checked against what the agent actually saw + did
    stock = next(e["result"] for e in run["events"] if e["tool"] == "get_inventory")
    order = next((e["args"][1] for e in run["events"] if e.get("is_action")), None)
    if order is not None and order > stock:
        return "ordered %d with only %d in stock" % (order, stock)

fl.scenarios(agent, [
    ("exact stock", {"item": "a", "qty": 3}),    # 3 of 3  -> ok
    ("one short",   {"item": "b", "qty": 3}),    # wants 3, has 2 -> must decline
    ("empty shelf", {"item": "c", "qty": 1}),    # 0 in stock -> must decline
], [never_oversell]).report()
# UNSAFE  one short   ordered 3 with only 2 in stock   <- a real bug, no lie required
```

A correct agent passes every case (no false alarm); a buggy one (e.g. glue code that ignores the model's
correct answer) is flagged on the honest cases. See it live: `python3 proof_demo.py`.

---

## 4. replay — catch a regression after a change

Record what your agent does today. After you change something (upgrade the model, tweak a prompt, bump a
dep), replay the recorded task — faultline flags where a *consequential* output silently changed.

```python
rec = fl.record(agent_v1, task="refund request #123")     # capture today's behavior

# ... later, after a model upgrade ...
fl.replay(agent_v2, rec, watch=lambda out: {"decision": out["decision"]}).report()
# ⚠ SILENT REGRESSION: decision 'DECLINE' -> 'REFUND' after the update
```

Traces persist to disk, so a real production run becomes a permanent regression test:

```python
from faultline.replay import save_trace, load_trace
save_trace(rec, "traces/refund_123.json")
fl.replay(agent_v2, load_trace("traces/refund_123.json"), watch=...).regressed()  # -> True
```

---

## 5. mine — let the tool learn the rules itself

Every mode above needs *you* to state the rule. `mine` learns rules by watching the agent on a handful of
known-good runs — which tools always get called, which always precede which, which output keys always
appear — then enforces them. A later regression trips a rule **nobody wrote**.

```python
spec = fl.mine(agent, good_tasks=["ship order #1", "ship order #2", "ship order #3"])
spec.report()
#  • tool 'validate_address' is always called
#  • 'validate_address' is always called before 'ship_package'
#  • output always contains key 'tracking_id'

# later, a refactor skips address validation:
spec.check(fl.run_once(broken_agent, "ship order #99"))
# ["mined rule broken: 'ship_package' ran without 'validate_address' before it"]
```

---

## 6. chaos — break its tools (resilience test)

Break a tool's return on purpose — wrong number, stale data, empty result, a 500 — and see whether the
agent has a *seatbelt* or quietly acts on the lie.

> **Honest note:** this mode injects a *fault*, so it's prone to "garbage in, garbage out" — feed an agent
> a wrong number and of course it may act on it. Treat a chaos failure as **"this agent has no guard,"**
> not **"this agent has a bug."** Its real value is *comparison*: a resilient agent (re-checks, refuses)
> passes the same fault a fragile one fails. For finding genuine agent bugs, prefer **scenarios** (mode 3).

```python
@fl.tool
def get_stock(item): return 2          # really 2 in stock

def agent(task):
    n = get_stock("widget")
    if n >= 10: place_order("widget")  # acts on whatever the tool reports
    return {"ordered": n >= 10}

fl.check(
    agent, task="restock widgets",
    faults=[fl.WrongNumber(factor=10, targets=["get_stock"])],   # make 2 look like 20
    invariants=[lambda run: "ordered out-of-stock" if run["output"]["ordered"] else None],
).report()
# ⚠ wrong-number  FAIL  [SILENT]   <- but note: the agent had no way to know 20 was a lie
```

Faults: `WrongNumber`, `StaleData`, `Truncate`, `NullResponse`, `Timeout`, `ServerError`.

---

## Beyond the modes — zero-config, frameworks, fabrication, drift

### `scan` — the zero-config front door
No suite file, no invariants. Wrap your tools, point it at your agent:
```bash
faultline scan my_agent.py:my_agent --task '{"sku": "A-12"}'
```
It discovers your wrapped tools, hits them with the default battery (WrongNumber, StaleData, Truncate,
NullResponse, EmptyResult, Timeout, ServerError), and runs the built-in detector — gates CI on exit code.
`result, tools = fl.scan(agent, task)` is the API form.

### `fl.assert_resilient` — drop into your existing tests
No plugin to install; it's a plain assertion that raises (with the full report) on any silent failure:
```python
def test_my_agent_is_resilient():
    fl.assert_resilient(my_agent, {"sku": "A-12"})        # faults=None -> the scan battery
    fl.assert_resilient(my_agent, task, faults=[fl.StaleData(targets=["get_price"])])  # or targeted
```

### Framework adapters — wrap the real tool seam
faultline wraps the actual callable your framework executes, so a fault genuinely reaches the tool:
```python
fl.instrument(graph_or_tools, actions=["place_order"])    # langgraph / langchain / llamaindex / pydantic-ai (idempotent)
# or be explicit: fl.instrument_langgraph(graph) / fl.instrument_langchain(tools) / fl.instrument_llamaindex(tools)
```
Verified against real installed **langgraph**, **langchain**, **llama-index**, and **pydantic-ai** (`tests/test_*_real.py`),
including a deterministic end-to-end catch on a real `create_react_agent` (`examples/langgraph_catch.py`).

### `tools_really_called` — catch a fabricated tool result
The #1 reported agent failure: the model *claims* it searched/queried and answers from a result it never
got. Because faultline owns the real transport log, that's deterministic to catch:
```python
fl.check(agent, task, faults=[...], invariants=[fl.tools_really_called(["search"])])
```
Fires only on a confident, non-abstaining answer with no real call. Abstention is keyword-detected; pass
your phrases: `fl.tools_really_called(["search"], abstain_markers=fl.DEFAULT_ABSTAIN_MARKERS + ("no hits",))`.

### `replay(transform=)` — drift after context compression
Re-run a recorded trace through a context transform (compression / rotation / a new prompt) and diff the
behavior — the "agent silently changed after compression" class:
```python
rec = fl.record(agent, task)
r = fl.replay(agent, rec, watch=lambda o: {"decision": o["decision"]},
              transform=lambda t: {**t, "context": t["context"][:512]})   # pure + deterministic
r.regressed()   # True if the decision silently flipped
```

---

## All six in CI

Each mode's result object has `.regressed()` / `.silent()` / `.breakers()` / `.violations()` returning
truthy on failure, so a test is one line:

```python
def test_agent_never_oversells():
    assert fl.scenarios(agent, honest_cases, [never_oversell]).safe()
```

Run the whole suite: `python3 tests/run_all.py` → **ALL GREEN ✓**.
