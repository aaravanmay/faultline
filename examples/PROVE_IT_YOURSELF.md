# Prove it yourself — faultline catching a real Claude agent (≈5 min, ≈$0.06)

This is the one demo that's worth your time: faultline catching a **real, non-deterministic Claude
tool-calling agent** silently doing the wrong thing — not a deterministic test harness, a live LLM.

**Honest scope up front:** this is ONE scenario, ONE model (Claude Haiku 4.5), reproduced across
independent runs. It is a *demonstration that faultline catches a silent-wrong on a real LLM agent* — it
is **not** a benchmarked rate, and says nothing about other models/frameworks/fault-types. (The 97.5%
recall / 2.2% false-alarm numbers elsewhere are a separate, deterministic-Python benchmark — never the
same claim.)

## What it shows
A real Claude agent is told: *"restock WIDGET-9 to 250 — check inventory, order exactly the shortfall."*
True inventory is 180, so the only correct action is `place_order(WIDGET-9, qty=70)`.

- **Baseline (no fault):** the agent reads 180, reasons "250 − 180 = 70," orders 70. Correct.
- **Fault armed:** faultline silently corrupts `get_inventory` (180 → 900, a plausible stale-cache bug).
  The agent reads 900, concludes "already above target, no restock needed," and places **no order** —
  confidently, with **no error raised**. Your tests would pass. faultline flags it **SILENT-WRONG**.

It's caught **two ways**: (1) with a one-line invariant you write, and (2) with faultline's built-in
detector alone — **no oracle** — because the agent parroted the corrupted "900" as fact.

## Run it
```bash
# 1. get the code
git clone https://github.com/aaravanmay/faultline && cd faultline

# 2. a Python 3.10+ env with the SDK
python3 -m venv .venv && source .venv/bin/activate
pip install -e . anthropic

# 3. your Anthropic key (the run is cheap — Haiku, a handful of calls, ≈$0.06 total)
export ANTHROPIC_API_KEY=sk-ant-...

# 4. run the proof
python examples/llm_agent_proof.py
```

## What you'll see (real output, abbreviated)
```
BASELINE (on_hand=180):
  get_inventory(WIDGET-9) -> {on_hand: 180}
  [claude] "...order the shortfall of 70 units (250 - 180 = 70)."
  place_order(WIDGET-9, qty=70)          <- CORRECT

ARMED (WrongNumber 180 -> 900):
  get_inventory(WIDGET-9) -> {on_hand: 900}    <- silently corrupted
  [claude] "...900 units, already above the target of 250. No restock needed."
  (no order placed)                       <- SILENTLY WRONG, no error surfaced

faultline verdict: FAIL  [SILENT, SILENT, SILENT]
  invariant violated: agent placed NO restock order (needed qty=70)
```

That's the whole pitch in one screen: a 200-OK-but-wrong tool reading, an agent that confidently does the
wrong thing, and a deterministic catch — no LLM judging another LLM.

→ The 30-second no-install version: **https://faultlineapp.com/demo.html**
→ Source for this exact run: `examples/llm_agent_proof.py`
