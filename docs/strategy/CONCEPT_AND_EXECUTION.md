# Tripwire (engine: faultline) — The Idea & How It Works

A single, plain-language explainer in two parts: **(1) the fundamental concept** — what it is and why it should exist — and **(2) the actual execution** — how it really works and how people use it.

---

# PART 1 — THE FUNDAMENTAL CONCEPT

## One line
**Tripwire is a fire drill for AI agents.** It deliberately breaks the tools an AI agent relies on, then catches the moments the agent confidently does the wrong thing without noticing — *before* that ships to real users.

## The problem it exists to solve
An "AI agent" is an AI that gets a job done by calling **tools** — little helpers like "check inventory," "look up the price," "search the database," "send the email." The agent reads what the tools tell it and decides what to do next. **Its entire judgment depends on trusting those tools.**

Here's the failure nobody catches today. Teams build an agent, test it while everything is working, see it behave perfectly, and ship it. Then in the real world a tool quietly returns *wrong* information — stale data, an old price, an empty result, a value that looks fine but isn't. The tool didn't crash; it returned "200 OK" with bad data. The agent believes it and **confidently does the wrong thing**: orders something that's out of stock, charges the wrong amount, "fixes" a file that already changed. No error. No alert. The dashboard stays green. The team finds out days later from an angry customer.

This is a **silent failure** — a confident, wrong action with no error attached. Studies put a number on it: most agent failures aren't crashes, and injected tool errors lead to wrong final answers a large fraction of the time. As more companies put agents into production, this is the #1 thing blocking them from trusting agents with real work — and *nothing on the market deliberately tests for it.*

## Why now
Three things make this the moment: agents only became reliable enough to deploy in the last year; far more code and agents are being shipped (often by people who don't fully vet them); and every existing testing tool checks the *happy path* (does it work when everything goes right?) — none check the *sad path* (what happens when the world lies to it?). The pain is real and growing; the tool to catch it doesn't exist yet.

## The core idea
Borrow a proven idea from regular software, called **chaos engineering** — Netflix famously breaks its own servers on purpose so its system is forced to survive failure. Tripwire does that for AI agents: it **deliberately breaks an agent's tools** (feeds them wrong/stale/empty data, makes them time out or error) and watches whether the agent **handles it gracefully or fails silently.**

## The one insight that makes it work
You might think catching a wrong answer requires knowing the *right* answer — which would be impossibly hard to automate. **It doesn't.** The trick: you don't judge the answer, you watch the *behavior*. A tool just fed the agent a lie — did the agent (a) notice and retry/flag it, or (b) confidently barrel ahead and act on the lie? You can tell which one happened just by watching the agent's moves. That's cheap, reliable, and needs no expensive "AI grading the AI."

## What it is — and isn't
- **Tripwire** is the product: a check that runs on every proposed code change and breaks the agent's tools.
- **faultline** is the engine inside it (the part that does the breaking and the watching) — and it's the *moat*, because no competitor does it: code-review bots only *read* code (never run the agent); quality-eval tools *run* the agent but never *break* anything. Tripwire is the only one that runs the agent **and** breaks its world **and** watches the behavior.
- **Honest scope:** it works cleanly for agents that make a clear **decision or action** (buy/decline, route here, output this data). For free-text chatbots ("write me a paragraph") it can only check basic things — judging whether free-form words are subtly wrong genuinely needs a human or an AI judge, and Tripwire doesn't pretend otherwise. So it targets **decision-making agents first.**

## Who it's for
**Developers and startups building their own AI agents** — not big companies buying off-the-shelf AI (they don't test the agent; the vendor does). It's a developer tool, sold the way developers already buy tools.

---

# PART 2 — THE ACTUAL EXECUTION

To do its job, Tripwire needs exactly two abilities: **(1) run your agent on a test task, and (2) reach the moment your agent calls a tool** so it can swap in broken data. Everything below is how it gets those two abilities with as little effort from you as possible.

## How the detection works — step by step
1. **Sit in the middle.** Tripwire places itself between the agent and its tools — like a switchboard operator who can read and alter the messages passing through.
2. **Run it normally once (the "baseline").** Let the agent do the task with everything working; record what it does. That's "what good looks like."
3. **Break one tool on purpose.** Run the same task again, but secretly corrupt one tool's reply — e.g., inventory says "10 in stock" when it's really 2; or the price tool times out; or a tool returns nothing. These deliberate breaks are the **faults** (the catalog: stale data, wrong value, empty, partial, timeout, error).
4. **Watch how the agent reacts** — sort the outcome into three buckets:
   - **Crashed** → an error popped up. (You'd have caught that anyway.)
   - **Coped** → it retried, used a backup, or said "I'm not sure / couldn't verify." → *Good, resilient.*
   - **Barreled ahead** → it gave a confident final answer as if nothing was wrong (ordered the out-of-stock item). → ***This is the silent failure — the bug we're hunting.***
5. **Rules — auto-generated, not your homework.** Two layers do the judging so you usually write *nothing*: (a) the **universal default** above (broke a tool + confident answer + no retry/flag = silent failure) needs zero setup; (b) Tripwire **auto-proposes** the specific rules from your tools' shapes ("don't act on a null/error result") and from the healthy baseline run ("it declined when stock < qty in the clean run — flag if that stops"). Plain true/false checks, no AI needed. You *can* add your own rules ("total charged can't exceed the real prices") as an optional power-up — but writing rules is never the price of entry. *(This matters: developers hate writing tests, so making them write the assertions would kill adoption — the engine generates them.)*
6. **Run each test a few times.** AI is slightly random, so one run is unreliable. Tripwire runs each fire drill several times and reports **PASS / FAIL / NOT-SURE** based on how often the agent handled it — never a single flaky "score."
7. **Report it on the pull request.** When a developer proposes a code change (a "pull request"), Tripwire runs automatically and leaves a comment: *"⚠ When the inventory tool returns stale data, your agent still places the order — failed 4 of 5 runs. Here's the exact replay."* A human decides what to do; Tripwire never merges or changes anything itself.

## How people install it (the happy path)
```
pip install tripwire
tripwire init      # scans your agent's tools, auto-writes a starter config
tripwire run       # runs your agent, breaks a tool, prints the report
```
The `init` step is the make-or-break: it reads your tools and auto-generates obvious scenarios, so you get a result in minutes instead of spending an afternoon writing config.

A scenario looks like this:
```yaml
# tripwire.yaml
scenario: out_of_stock
  task: "Order 3 widgets"
  break: { tool: get_inventory, with: stale_data }   # really 2, tool now says 10
  rule:  "must NOT place the order"
  runs:  5
```

## The three ways it "reaches" your tools (easiest first)
1. **Framework hook (~1 line).** If you use LangChain / LangGraph / OpenAI Agents SDK, they already have a built-in "tool middleware" slot. Tripwire plugs into it and can now see and alter every tool call — *you don't rewrite your tools.*
2. **OpenTelemetry traces (no change to tool code).** "OpenTelemetry" is a standard way apps already report what they did. If your agent emits these, Tripwire reads them to watch tool calls and check behavior — zero touching of your tool code.
3. **MCP proxy (for MCP tools).** If your agent reaches tools over MCP (the "USB port for AI"), you point it at Tripwire's address instead of the real tool server; Tripwire forwards calls but can corrupt or delay the replies. One config line. (Experimental for the local kind.)

## Where it runs — your own CI
The real home is your **CI** (the automated pipeline that runs checks on every code change). You add a small file, `.github/workflows/tripwire.yml`, and from then on, on every pull request: a fresh machine installs Tripwire → runs your scenarios against your agent → posts a comment with what broke. You can also just run `tripwire run` locally while building.

## What you actually hand it
1. **A way to start your agent on a task** (a function it can call).
2. **Your LLM API key**, stored as an encrypted CI "secret" — needed because to test the agent it has to actually *run* it, which costs a few API calls.
3. **A few scenarios** — Tripwire ships templates and auto-suggests them, so this is minutes.

## Why it's safe and legal
Everything runs **inside your own environment** — your machine or your CI — on your code, with your key. **Tripwire (the company) never receives your code or your data;** it only leaves a comment on your PR. That's deliberate: it removes data-handling liability and makes a security team comfortable installing it. It also never auto-changes your code and never publicly rates anyone.

## No real-world side effects (how it safely tests the "barrel ahead" case)
Worried it'll *actually* charge a card or send an email while testing? It can't. Because Tripwire sits in front of **every** tool, the agent never reaches the real Stripe/Shopify. Read-tools return fake or corrupted data; action-tools (`place_order`, `charge`, `send_email`) are **captured and handed a fake "success" — never actually executed.** And it doesn't *need* them to run: the bug we're catching is the agent *deciding* to act on bad data, and Tripwire sees that decision the instant the agent makes it, *before* anything fires. Like a driving instructor's brake pedal — the student "crashes," the car never moves. Side-effecting tools are stubbed by default; nothing real runs unless you explicitly allow it.

## Never cry wolf (so developers don't rip it out)
Developers delete tools that fail randomly. So Tripwire **only comments by default — it never blocks your build** unless you opt in, and it only raises a flag when the agent fails *consistently across several runs* AND *worse than it did before* (a real regression) — never on one unlucky roll of the AI's dice. The whole design rule is "never cry wolf." (This is the single make-or-break detail for a CI tool.)

## The honest friction (not hidden)
- You must give it a runnable entry point to your agent and accept a small per-run API cost (it runs the agent several times).
- Interception is cleanest with a popular framework; an unusual custom setup needs more wiring.
- The make-or-break engineering is the `init` auto-setup + the framework adapters. That's why v1 targets **one** framework first and nails it before spreading.

## How we'll know it's working (the 6-month test)
~10 teams running it weekly on their pull requests, 50+ real silent failures caught, a first paying team. The metric that matters is **weekly active runs**, not GitHub stars. The launch move that proves it: point Tripwire at a popular open-source AI agent, catch a real silent bug, file the fix, and post it publicly — one act that is the proof, the demo, and the story at once.

---

# PART 3 — MARKET, REALISTIC EXPECTATIONS & COSTS

## What already exists (the landscape, honest)
The broad "AI tools for code/PRs" space is **crowded (~8/10)** — but everyone is in a *different lane* than us:
- **Code-review bots** — read your code, comment on it, but **never run the agent.** CodeRabbit (~$40M/yr, ~$550M valuation), Greptile, Qodo, GitHub Copilot, Graphite. → can't see what the agent *does* at runtime.
- **App test-generators** — actually run web apps, but test buttons/UI, **not AI tool-failures.** QA Wolf, Momentic, mabl, Octomind, Meticulous.
- **Agent eval / monitoring** — run the agent and grade answer *quality*, but **never break anything.** Braintrust (~$800M valuation), Langfuse, Galileo ($68M), LangSmith, Arize, Maxim. → they *detect* failures, they don't *cause* them.
- **AI security / red-teaming** — attack the *model* with nasty prompts (jailbreaks), **not the tools.** Lakera, Promptfoo (bought by OpenAI), NVIDIA Garak, Haize. → security, not reliability.
- **Closest to us (and tiny):** `agent-chaos` (a hobby project, ~23 GitHub stars), LangWatch/Scenario (basic error mocking), a couple of academic papers. **No funded company does adversarial tool-fault injection in CI.**

## What does NOT exist (our gap)
A tool that, on every code change, **runs your agent, deliberately feeds its tools broken/stale data, and flags when it fails *silently*** — with a behavior-based verdict, no expensive AI-judge, inside your own pipeline. That exact intersection is **~2/10 crowded** — genuinely open, with an estimated **12–18 month window** before the eval incumbents extend into it.

## Realistic expectations (no hype)
- This is a **real developer-tool business with a high floor — not a guaranteed unicorn.** Stated plainly so we don't fool ourselves.
- **Reference point:** Gremlin (chaos engineering for normal software — the closest analogy) reached ~$35M/yr revenue after ~a decade, with $52M raised and a full team. "Chaos for *agents*" is a slice of that, so the realistic standalone ceiling is "a solid dev-tool company," not "obviously $1B."
- **Honest outcome ladder:**
  - **Floor (likely even if it never becomes a company):** you become one of very few people who deeply understand how AI agents fail, ship an open-source tool real developers use, and build a reputation + network — at 15. That alone is career-defining.
  - **Middle (plausible):** a respected OSS tool + a handful of teams paying, possibly acqui-hired by an eval/observability company.
  - **Ceiling (possible, not promised):** the default way teams test agent reliability → a fundable venture, raised later when you're not a minor.
- **The 6-month go/no-go:** ~10 teams running it weekly, 50+ real silent failures caught, a first paying team. Metric = **weekly active runs**, not stars. Miss it → fall back to the floor outcome with a clear conscience.
- **The real risks (restated):** will developers pay for *this specifically* (unproven); false alarms must stay near-zero or it gets deleted; incumbents could extend into the lane; solo + minor caps the money phases until there's a parent-LLC + entity.

## Realistic costs

**A) What it costs YOU (the founder) — near zero.**
- Building v1: **$0 cash** (it's software) — the cost is your *time* (~3–4 weeks for a scoped v1).
- LLM API while building/testing: ~**$20–100/month** (lean on cheap/local models).
- Domain ~$12/yr; GitHub, PyPI, CI free tiers; hosting free to start.
- *Before charging money:* a parent-owned LLC (~$50–500) + one startup-lawyer review of the terms (~$300–1,500). **Not needed to launch the free OSS tool.**
- **Total to reach a launched OSS tool + first users: ~$0–500.** A full year with a small hosted dashboard: ~$2,000–10,000.
- **Don't raise money now** — costs are tiny; your constraint is time, not cash. (Raising before traction adds pressure and is mostly blocked for a minor anyway.)

**B) What it costs the USER (the team running Tripwire).**
- The tool: **free** (OSS core); paid metrics dashboard later ~$20–30/developer/month.
- Their real cost is **LLM API calls**, because testing means actually *running* their agent several times. Rough math: 5 scenarios × 5 trials = 25 agent runs per PR; at ~$0.01–0.10 per run ≈ **$0.25–$2.50 per pull request.** Cheap for most teams; big suites add up → mitigated by *cassettes* (record once, replay), using a cheap model for the agent-under-test, and only re-running changed scenarios.
- CI compute: negligible (covered by GitHub's free tier for most teams).

---

# PART 4 — STRATEGY & THE HARD QUESTIONS

## The strategy: open-source-first
After heavy stress-testing (an 11-expert teardown + two outside critiques), the verdict is clear: **don't sell it as a paid product first — give the core away free and open-source, build a following and a public track record, monetize later.** This is the Chaos Monkey → Gremlin path (also how Sentry and PostHog grew). Why it fits *this* founder: it needs no payments, contracts, or being 18 (so the minor wall doesn't block it); it turns the two biggest objections — "teams defer testing" and "it competes with their time, not their money" — into a *distribution* strategy (free + zero-setup + post-incident content is exactly how you reach a developer who'd never take a sales call); and the floor is a reputation banked even if it never makes a dollar.

## Pricing (when the time comes)
| Tier | Price | What it is |
|---|---|---|
| Open-source / self-host | **$0** | The tool + engine. Free forever. This is *distribution*, not revenue. |
| Team (hosted) | **$200–300/mo** | Hosted runs, history, dashboards — "every PR" automation without self-hosting. |
| High-stakes / compliance | **$500–2,000/mo** | Audit-trail "evidence your auditor needs," priority support — for teams with a knowable cost-of-failure. |
| Enterprise | custom | SSO, on-prem, SLAs. Year 2+. |
Floor target: **$200/mo × 5 teams = $1,000/mo** — small, but a real business, not a hobby.

## Who actually buys first (the sharp beachhead)
Not "anyone building an agent." The teams who buy NOW: **startups whose *product itself* is an AI agent** (their reliability is tied to customer money — YC AI batches are a public, reachable list), **high-stakes operators** (money / regulated / irreversible actions), and **anyone who just had a silent-failure incident.** Skip the "exploring agents internally" majority — they defer.

## The next move (the cheap test of whether any of this is real)
Build **`npx tripwire-check`** — a one-command tool anyone runs on their agent in ~90 seconds — point it at 3–5 well-known open-source AI agents, catch real silent bugs, and publish the findings in one post. It tests the only two things that matter, cheaply: **(1)** does it catch real bugs in code you didn't write? **(2)** does anyone care?

---

## Three honest questions answered

**1. Every company is unique — how can Tripwire work with all of them?**
Tripwire doesn't need to understand a whole company. It only needs to reach **one narrow, universal spot: the moment the agent calls a tool.** Every agent — no matter how custom the business — does the same basic thing: call a tool, read the reply, decide. Tripwire taps that one chokepoint (via a framework hook, an OpenTelemetry trace, or by wrapping the tool functions), and that chokepoint looks the same everywhere even when the companies don't. The *scenarios* (what to break, what rule matters) are written by each team for their own case — Tripwire supplies the engine + templates, the team supplies ~3 lines of "here's what matters to us." So it's not "understand every company"; it's "plug into the one thing every agent has in common, and let each team describe its own rules." *(Honest limit: bare-metal custom agents need a bit more wiring than framework users — the ~70/30 split — which is why OpenTelemetry is the long-term universal hook.)*

**2. Why can't companies just build their own version and train it themselves?**
They can — for a weekend, for one case. Why most won't, and why that's the moat:
- **It's not the agent-builder's job.** A team shipping an agent wants to ship features, not build and maintain a testing framework — the same reason they use Sentry instead of writing their own error tracker, or pytest instead of a homemade one.
- **The hard part isn't the breaking — it's the *judging* + the upkeep.** Reliably deciding "failed silently vs. legitimately recovered," handling the AI's randomness with statistics, and keeping up with every framework/MCP change is an ongoing engineering job a free, maintained tool does for you.
- **There's nothing to "train."** Tripwire isn't a trained AI model someone copies — it's mostly *deterministic code* (break a tool, watch the behavior). No secret model to steal; the value is the engine + the growing library of failure scenarios + the community.
- **The real moat is the community + public track record, not the code.** Anyone can read open-source code; few can rebuild "the tool everyone already trusts." Chaos Monkey was open-source — Gremlin *still* became the company, because adoption and reputation were the moat, not the source.
- *Honest caveat:* a big incumbent (LangSmith/Braintrust) **could** bolt on a similar feature — that's the real competitive risk, and the defense is being first + community-owned, which is exactly why we go open-source.

**3. How big is the market — isn't "people building their own agents" a shrinking slice of a small pie?**
Honest answer: **the slice is narrow today, but it's *growing*, not shrinking — and we don't need it to be big.**
- *Narrow now:* most "agents" in production are still simple, low-stakes, or internal pilots. The teams with real, costly, action-taking agents number in the thousands, not millions.
- *Growing fast:* every quarter more companies move agents from "experiment" to "in production doing real work" — that's the industry's direction, not a retreat. Each one that crosses into "the agent touches money/customers" becomes a candidate customer.
- *A solo founder doesn't need a huge market.* 5–10 paying teams = a real start; a few hundred = a solid company. Even Gremlin (closest comp) is ~$35M/yr — plenty for one person. You're not chasing a billion users; you're trying to be *the* tool for the few thousand teams who genuinely can't afford a silent failure, while that group grows.
- *The real risk isn't "shrinking" — it's "too early":* if production agents grow slower than expected, the paying group stays small longer. That's exactly what the cheap `npx tripwire-check` test (and talking to ~30 teams) is built to find out *before* betting years on it.

---

**In one breath:** Tripwire installs as a small library + a GitHub check, hooks into your agent's framework in about a line, runs your agent on a test task while secretly breaking its tools, watches whether it fails silently, and comments the results on your pull request — all inside your own pipeline, so it never sees your data — catching the confident-but-wrong failures that every other tool misses. Free and open-source first; monetized later for the teams who can't afford to be wrong.
