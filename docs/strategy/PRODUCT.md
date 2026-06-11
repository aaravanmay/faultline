# Tripwire (engine: faultline) — Product Doc v2 (post-teardown, hardened)

*v2 supersedes the v1 framing. Rewritten after 11 expert teardowns + fix research. Reality-first. Companion docs: TEARDOWN.md (the attack), REBUTTAL.md (concede/fight), CHANGELOG.md (what changed v1→v2).*

## One-liner
**Tripwire — the PR check that breaks your agent on purpose.** On every pull request it runs your AI agent/app, adversarially degrades its world (tools return stale/empty/partial data, time out, or error), and tells you if the agent *fails silently* — confidently does the wrong thing with no error. **"faultline" is the adversarial engine inside it; that sad-path testing is the moat.**

## Reality check (read first)
- **Proven:** developers pay for PR-integrated tools (CodeRabbit ~$40M ARR / 8,000+ paying; Qodo, Graphite, QA Wolf $15–20M ARR). WTP ≈ $20–50/dev/mo, self-serve, no procurement. Silent agent failure is a documented, escalating, funded problem.
- **The bet (unproven):** that enough teams will adopt+pay for *adversarial sad-path testing of AI features in CI specifically*, soon, and that a solo founder can ship a genuinely useful version. 6-month signal decides it.
- **Honest competitive truth:** "AI PR-testing" broadly is **8/10 crowded** (CodeRabbit $550M, Greptile, Qodo, Copilot, Braintrust $800M, Galileo). The **specific wedge — adversarially testing AI features/agents on every PR for silent operational failures — is ~2/10**: code-review bots do static diffs (never run the app); eval platforms gate on quality but **don't inject faults**; the one near-overlap (LangWatch/Scenario, OSS, €1M) does only exception-level mocking. Window ~12–18 months.

## The problem
Teams ship agents that pass every demo. In production a tool returns stale data (`200 OK`, looks fine) or fails, and the agent **confidently does the wrong thing** — orders out-of-stock goods, uses a stale price, "fixes" a file that changed — no error, dashboard green, found days later. "78% of agent failures aren't crashes." Reliability is the #1 blocker to shipping more agents, yet nobody tests the sad path at PR time.

## Who it's for
**Developers and AI-native startups building their own agents/AI features** — self-serve, OSS-first, in the PR workflow. NOT enterprise-SRE buyers (a solo minor can't sell there) and NOT buyers of off-the-shelf SaaS AI.

## What it does (the loop)
On each PR: **run** the agent on a small golden task → **inject** a fault at the tool boundary (stale / empty / partial / wrong-schema / timeout / error) → **check** behavior with developer-written invariants + structural + trajectory checks → **verdict** PASS / FAIL / INCONCLUSIVE (statistical, multi-trial) → **PR comment** showing exactly what broke, with a repro. Human decides whether to merge.

## The honest detection (scoped to what actually works)
- **Scope: structured/decision agents** (typed actions / JSON / tool-calls / routing / SQL). Free-text agents get structural checks only — **no LLM judge in the core** (it would add cost + non-determinism to the tester itself). Said plainly in the README.
- **Three sound check types:** structural (valid output, no null required fields), **developer-written behavioral invariants** ("if inventory tool empty → must not place order"), trajectory ("validate before submit"). Provenance is a secondary signal.
- **Non-determinism handled honestly:** multi-trial with Wilson confidence intervals + SPRT early-stop (single-run binary = 0% regression-detection power; statistical = 86%). **Three verdicts, never a single gameable "score."**
- **Tiered interception (not "patch all networking"):** (1) in-process tool mocking via the framework's own hook (LangChain `wrap_tool_call`); (2) **OpenTelemetry trace assertions** — framework-neutral; (3) MCP HTTP proxy — experimental.

## The defensible wedge
**"The PR gate that runs your agent against broken tools, degraded APIs, and stale data before you merge."** Defensible because: static-review bots *can't run the app*; eval platforms *don't inject faults*; it requires genuinely different engineering (run app + realistic faults + grade non-deterministic output). Own the developer-native CI surface + OSS community before incumbents extend into fault injection.

## Competition (grounded, live)
- Static PR review (no app run, no faults): CodeRabbit, Greptile, Qodo, GitHub Copilot, Graphite, Ellipsis.
- E2E test-gen (runs web apps, not AI faults): QA Wolf, Momentic, mabl, Octomind, Meticulous, Diffblue.
- Agent eval in CI (quality gates, **no fault injection**): Braintrust ($800M), Galileo, LangSmith, Langfuse, Maxim.
- Adversarial specialists: Promptfoo (→OpenAI; *security* not reliability), General Analysis (security), Antithesis ($152M; *infra* fault injection, not AI). LangWatch/Scenario (OSS, exception-level mocking) = closest, tiny.
- **The intersection — operational fault injection for AI features on every PR — has no funded incumbent.**

## Business model
Free OSS core (CLI + GitHub Action) → paid hosted **metrics-only dashboard** (pass/fail trends, *no agent data*) ~$20–30/dev/mo → team tier later. The Promptfoo/CodeRabbit OSS→paid playbook. Devs adopt; eng leads pay.

## The honest v1 (smallest thing that's real)
One framework first (LangGraph or OpenAI Agents SDK), six fault types, in-process + OTel interception, three-verdict statistical engine, GitHub Action that posts a PR comment, comments-only (no merge-block by default). `tripwire.yaml` scenarios. Target: <5 min to first value.

## Go-to-market (solo-founder-reachable)
**The "living demo":** point Tripwire at a popular OSS agent repo, catch a *real* silent failure, file the PR with the scenario, write it up, **Show HN** ("I built a tool that caught a silent failure in [popular agent]"). Then: respond to every issue in 24h (a solo teen's real edge), seed r/LangChain / r/LocalLLaMA / framework Discords, weekly "agent failures in the wild" writeups. Contribute the fault taxonomy upstream to OpenTelemetry GenAI.

## Legal guardrails (hard)
Self-run OSS only; comments-only; **never** store agent content; **never** publicly rate named third parties; **never** auto-patch prod; hosted tier is metrics-metadata only. Parent-managed LLC + the safe scope before any money/audits.

## Risks / what must be true
1. Teams adopt+pay for sad-path AI testing specifically (test via the living demo + first paying team). 2. The scoped detection has low false positives (make-or-break). 3. We move faster than Braintrust/Galileo adding fault injection (12–18mo window). 4. Solo execution: the sandboxed agent-runner is the hard part → narrow scope hard. 5. Minor/legal: stay self-run until parent-LLC.

## 6-month signal (go/no-go)
~10 teams running it weekly on PRs, 50+ real silent failures caught, 3 "we'd have shipped that" testimonials, first paying team. Metric = **weekly active runs**, not stars. Miss badly + no one pays + no one re-runs → pivot to the high-floor credential outcome (expertise + OSS + reputation) with a clear conscience.

## One-line summary
**Tripwire is the PR check that adversarially breaks your AI agent's tools to catch silent failures before you merge — faultline is its engine and its moat; it lives in the 2/10-crowded gap inside an 8/10-crowded market, is honestly scoped to structured/decision agents with a statistical three-verdict (no magic score), ships self-run + legally clean, sells to developers who already pay for PR tools, and has a real 6-month signal — a genuine dev-tool business with a high floor, not a guaranteed unicorn.**
