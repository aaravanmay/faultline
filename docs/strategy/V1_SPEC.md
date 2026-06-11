# `npx tripwire-check` — v1 Spec (the proof-of-concept)

The first artifact to build. One command, ~90 seconds, zero config. Its job is not to be the product — it's the **cheapest possible test of the two questions that decide everything:** (1) does faultline catch *real* silent failures in code the founder didn't write? (2) does anyone care? Buildable solo in days, no sales, no capital, no being-18.

## What it is
```
npx tripwire-check <path-or-known-agent>
```
Point it at an AI agent (a local repo, or a built-in adapter for a known one like browser-use). It runs the agent on a sample task, **breaks the agent's tools on purpose**, watches whether the agent fails silently, and prints a report + a shareable markdown summary. No account, no API to us, runs entirely on the user's machine.

## Scope (v1 — honest, narrow on purpose)
- **In:** structured/decision agents (ones that take actions / call tools / output a decision) built on **one supported framework first** (pick the one the first target uses — likely a browser-use / LangChain-style tool loop).
- **Out (v1):** free-text-only chatbots (we can't judge prose quality without an LLM); deeply multi-agent / long-looping flows (best-effort only — see "Honest limits").
- **One target at a time:** v1 ships with a hand-built adapter for the *first* repo we attack (browser-use), then generalizes.

## The pipeline (end to end)
1. **Attach** — point at the agent via a built-in adapter (browser-use first) or a 1-line wrap of its tool entry point. Interception happens at the tool boundary (or via OpenTelemetry if the agent emits traces).
2. **Auto-discover + auto-generate (zero human rules — the Gemini fix).** Read the agent's tools/tool-schemas, then auto-create scenarios *and* assertions so the user writes nothing:
   - **Universal default (no schema needed):** the trajectory check — *broken tool used → confident final action → no retry/fallback/uncertainty = SILENT FAILURE.* Works on every agent out of the box.
   - **Schema-derived assertions:** "must not act on a `null`/error tool return"; "output must match the declared schema."
   - **Baseline-derived assertions:** run the agent healthy once, infer invariants from how it *normally* behaves ("it declined when stock < qty in the clean run → flag if that behavior disappears under a fault").
   - (Hand-written rules remain an *optional* power-up, never a requirement.)
3. **Baseline run** — run the task with all tools working; record the agent's behavior + every tool input/output into a **cassette** (so later runs are reproducible and offline).
4. **Fault sweep** — replay the task, injecting one fault at a time from the catalog × each tool the agent actually used.
5. **Detect + judge** — classify each run PASS / FAIL(silent) / CRASH / INCONCLUSIVE using the behavioral checks + assertions, run each a few times (multi-trial), and apply the **never-cry-wolf rules**: comment/report only (never block), and only call FAIL on a *consistent* failure that's *worse than baseline*.
6. **Report** — terminal output + a clean `tripwire-report.md`:
   ```
   faultline · resilience report for browser-use (demo task: "buy a product")
   ============================================================
   baseline: ✓ correct
   ⚠ stale-page on get_page → agent confidently clicked "Buy" on an out-of-stock item   (SILENT, 4/5 runs)
   ✓ timeout on get_page → agent retried, then reported failure                          (handled)
   ============================================================
   Resilience: 2/6 faults handled.  1 SILENT failure (the dangerous kind).
   ```

## The fault catalog (v1)
Silent (data is wrong, no error): **stale-data, wrong-value, empty, partial, null.** Hard (tool blows up): **timeout, server-error.** Each can target a specific tool (`--tool get_page`) or sweep all.

## No real-world side effects (built in)
Every tool is intercepted, so the agent never reaches the real internet/Stripe/etc. Read-tools return cassette/corrupted data; **action-tools are captured and given a fake success — never executed.** The "did it barrel ahead" verdict is read off the *attempt*, before anything fires. (Driving-instructor brake pedal.)

## What the user provides
1. The target agent (a repo + a one-line "run it on this task," or use a built-in adapter).
2. An LLM API key (env var) — to actually run the agent a few times.
That's it. No config file required for the default run.

## The launch plan (the whole point)
1. Build the adapter for **browser-use** (~92K stars, most tool-dependent, most visceral demo). Find a real silent failure.
2. Repeat for **GPT Researcher** (search/scrape → confident report on broken data) and **OpenHands** (coding agent acting on stale files).
3. For each real bug found: file a **friendly PR with a fix + a regression test** (welcomed OSS contribution — we ran their open code locally; legally clean). Never a "gotcha."
4. One write-up: *"faultline found & fixed silent failures in browser-use / GPT Researcher / OpenHands — here's how."* → Show HN / Reddit / the frameworks' Discords.
5. Watch the two signals: do maintainers merge the fixes (it works), and do devs say "run it on mine" (they care).

## Honest limits (v1)
- **Multistep is best-effort.** A fault on turn 1 surfacing as a silent failure on turn 8 is hard to attribute; v1 leans on OpenTelemetry trace/span IDs where present and otherwise focuses on shorter flows. Not solved — flagged.
- **One framework first.** The clean experience only exists for the target's stack initially; broad support comes later.
- **Free-text agents** get only structural checks, not semantic judgment.
- **Auto-generated assertions won't be perfect** — they propose; the universal trajectory check is the reliable floor.

## What it would prove (and why it's the right next move)
- If it can't find a real silent failure in browser-use/GPT-Researcher/OpenHands → the core thesis is weak, learned in **days for ~$0**.
- If it finds real bugs *and* the "run it on mine" replies come → that's the green light, and the artifact is simultaneously the proof, the demo, the founder-story, and the warm-inbound for the 30 customer-discovery chats.

## Build estimate
Solo, ~1–2 weeks for a scoped v1 against one target (interception + cassette + fault sweep + trajectory detection + report). The interception primitive is the flightlog code, reused.
