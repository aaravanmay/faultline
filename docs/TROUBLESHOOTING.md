# Troubleshooting

The friction points people actually hit, with the fix. (Full scope + limits: [CAPABILITIES.md](../CAPABILITIES.md).)

### "no faultline-wrapped tools fired" / `scan` exits 2 before testing anything
faultline can only break tools it can see. Wrap your tool calls:
```python
@fl.tool
def my_tool(...): ...
action = fl.wrap(my_action, is_action=True)   # for tools with real side-effects
```
Then run **`faultline doctor FILE.py:agent`** — it tells you upfront which tools fired and whether faultline can test the agent, before you run a full scan.

### A fault shows "fault never reached the agent" / a PASS that feels too easy
That's a **coverage gap, not resilience**. Two causes:
1. **The agent didn't call that tool** on this task — give it a task that exercises the tool.
2. **The tool returns an uncorruptible type** — a generator/iterator (streaming), a coroutine, or a custom object / dataclass / pydantic model. The value-corruption faults reach dict/list/tuple/str/number (and Decimal, and pandas), not those. Fix: **materialize** the return (`list(stream())`) at the wrapped boundary, or assert an **invariant** that checks the final decision instead.

### "faultline received a coroutine — async agents aren't supported yet"
faultline is sync-only today. Wrap your async agent in a sync shim:
```python
fl.check(lambda task: asyncio.run(my_async_agent(task)), ...)
```
(An async *tool* is also uncorruptible for now — same coverage-gap as above.)

### A buggy agent shows PASS even though it oversold / acted wrong
If your invariant reads a **mutable argument** (e.g. `event["args"][0]`) and your agent mutates that object *after* the call (`cart.clear()`), the recorded args reflect the post-mutation state. **Read the agent's output / decision, not mutated input objects** — `{"ordered": qty}` beats inspecting the cart you later emptied.

### My LLM agent's free-text answer trips the detector (a false positive)
The zero-oracle detector is strongest on **structured outputs and actions** (a number, a chosen action). Free-form prose that happens to echo a value can read as parroting. Fix: have the agent return a **canonical decision field** (`{"decision": "...", "amount": ...}`) and assert an **invariant** on that, rather than relying on the heuristic over prose. Use **`scan --explain`** to see exactly what was corrupted and why it flagged — most "false positives" are the agent genuinely acting on the bad value.

### A *correct* agent gets flagged FAIL (a real false-positive class)
Two known cases (see CAPABILITIES.md): a **safe-fallback constant** that coincidentally differs from baseline by the injected amount, and a **fail-safe escalation** (the agent pivots to a new safe action like `alert_ops`). The detector can't tell these from a real divergence. Add an **invariant** that encodes "this fallback/escalation is fine" to disambiguate.

### Is this verdict real? — use `--explain`
```bash
faultline scan my_agent.py:agent --task '{...}' --explain
```
It prints, for every FAIL/CRASH, exactly what faultline corrupted (tool, before → after) and what the agent then did. A verdict you can audit, not a black box.

### Money values weren't getting corrupted
Fixed — `WrongNumber` now corrupts `Decimal` (the standard money type), not just int/float.

### It says my agent "CRASHED" under a fault
That's a real finding too (CRASH ≠ PASS): the agent threw when a tool returned bad/empty/None data instead of handling it. Add a guard (validate / default / abstain) so bad data degrades gracefully instead of crashing.
