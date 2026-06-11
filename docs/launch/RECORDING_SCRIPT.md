# faultline — 60-second demo recording script (live-frameworks version)

**The clip:** a tool that breaks the 8 biggest AI-agent frameworks on purpose and catches them
silently doing the wrong thing — live, via the API, for pennies. Ends on the scoreboard.

**Setup**
- Terminal, big font (18-20pt), dark theme, ~90 cols. `cd faultline`.
- `ANTHROPIC_API_KEY` in `.env` (the demo makes ~4 real Claude calls, ~1 cent).
- One command runs the whole thing: `FL_DEMO_SLEEP=1.3 python3 demo.py`
  (`FL_DEMO_SLEEP` controls pacing; raise it to slow down, set 0 for a dry run.)

---

## Shot list (~55s)

**0:00–0:09 — hook** (talk over the banner)
> "AI agents don't usually crash. They fail *silently* — a confident, wrong answer with a 200 OK.
> Your evals pass it. Then it does the wrong thing in production."

**0:09–0:18 — the idea** (the two narration lines print)
> "faultline breaks an agent's tools on purpose — wrong data, empty data, stale data — and catches
> the moment the agent quietly believes it."

**0:18–0:33 — the LIVE catch** (the `live_ops_agent` block runs for real)
> "Right now it's driving a real Claude order-bot, feeding it a *wrong* stock number, and watching.
> The agent places an order it would never place on the real number — and faultline flags it.
> That's the tool's own detector. No human, no LLM-judge."
- Point at the `⚠ wrong-number FAIL ... took action on corrupted data` line and `(real Claude API calls: 4)`.

**0:33–0:48 — the scoreboard** (the 8-framework table prints)
> "Now point it at the eight most popular agent frameworks — LangGraph, pydantic-ai, agno,
> LlamaIndex, AutoGen, CrewAI. Seven of eight: caught silently failing, live. smolagents passed —
> and that honest pass is what makes the rest trustworthy."

**0:48–0:55 — close**
> "Deterministic. Runs in your CI. The whole board cost about ten cents. It's open source."
- Land on: `7 / 8 frameworks — the TOOL caught a silent failure, live.`

## On-screen captions to burn in
- `200 OK ≠ correct`
- `the tool did the finding — not a human, not an LLM-judge`
- `7/8 frameworks, live, ~10¢`

## Two cuts
- **15s version:** just `FL_DEMO_SLEEP=0` → the scoreboard + the closing line.
- **Full proof (for a reply/thread):** `python3 bench/tool_caught/run_all_live.py` running all 8 live.

## Don't
- Don't claim a merge/partnership with any framework. It's "caught silently failing under a broken tool."
- Don't hide that smolagents passed — lead with it; it proves no fake alarms.
- Don't show `.env`.
