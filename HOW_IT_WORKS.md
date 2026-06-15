# How faultline Works

*Plain-English reference for the whole tool — every part traced to the real code. One running example, a support/inventory agent for a small online store, keeps it concrete.*

## 0. What problem is this even solving?

Picture the support agent for your store. A customer writes in: *"My order ORD-1001 arrived broken, I want a refund."* The agent looks up the order, checks the refund policy, and issues the refund. Normal stuff.

Now picture one tiny thing going wrong **inside a tool**, not inside the agent's brain:

- The orders database had a caching bug and returns the **wrong amount** — it says the customer paid `$210` when they really paid `$42`.
- The agent has **no way to know** this number is wrong. It looks completely plausible. So it cheerfully refunds `$210`.
- No exception is thrown. No error log. The tests pass. The dashboards stay green.

That is a **silent failure**, or a "200-OK-but-wrong": the tool returned `200 OK`, the agent did something confident, and the something was wrong — and **nothing anywhere raised its hand.**

Ordinary tools cannot catch this:
- **Unit tests** check the happy path — good data in, good answer out.
- **Evals** *measure* quality on normal inputs. They don't break a tool mid-run.
- **Monitors** watch for errors and crashes. A silent-wrong throws no error, so monitors see nothing.

faultline's job is to **deliberately make reality go wrong** — feed the agent stale data, wrong numbers, empty results, timeouts — and **catch the exact moment the agent confidently does the wrong thing with no error.** A fire drill for your agent: start the fake fire on purpose, in a safe place, and find out whether the agent has a smoke detector before the real fire hits production.

---

## 1. The one idea: record, corrupt, judge

Everything in faultline is built on **one trick**. Understand this section and the other five are variations on it.

### The trick: wrap the tool so faultline sits in the middle

When you write a tool, you mark it with `@fl.tool`:

```python
import faultline as fl

@fl.tool
def get_order(order_id):
    return ORDERS.get(order_id)      # your real database lookup
```

`@fl.tool` does **not** change what `get_order` does in normal life — outside a faultline run the wrapper is completely transparent, so you can leave it on in production. But it replaces your function with a wrapper that sits between the caller (your agent) and the real function. That single position — *in the middle of every tool call* — is what makes the whole product possible. faultline can: **watch** the call, **corrupt** the return value on its way back, and **record** everything.

The wrapper only watches/corrupts **when a faultline session is active** (armed via a per-thread `contextvars` flag, so parallel runs don't collide). No session → pass-through.

### Two kinds of tools: "reads" and "actions"

- **Read tools** (`@fl.tool`): fetch information (look up an order, search docs, check stock). No real consequence. During a test faultline **really calls them**, so the agent gets real data it can then choose to corrupt.
- **Action tools** (`fl.wrap(fn, is_action=True)`): do something irreversible (issue a refund, send an email, place an order). During a test, faultline **never calls the real function** — it returns a harmless stub and records *that the agent tried to act, and with what arguments.*

```python
def _issue_refund(order_id, amount): ...        # the REAL refund — moves money
issue_refund = fl.wrap(_issue_refund, is_action=True, name="issue_refund")
```

This is the safety guarantee: **run a thousand chaos tests against your refund agent and not move a single real dollar.** faultline captures the *intent* to act without letting it fire. (Section 5's runtime "guard" is the mirror image — there the real action fires unless a rule blocks it.)

### The run record — the "diary"

Every single run produces a **run record** — the most important data structure in the project, because every detector, mode, and report reads from it. Three top-level fields:

```python
{
    "events": [ ... ],   # every tool call, in order
    "output": <whatever the agent returned at the end>,
    "error":  <the exception the agent threw, or None>,
}
```

Each event in `"events"` is one tool call:

```python
{
    "tool": "get_order",                # which tool
    "args": ["ORD-1001"],               # positional args
    "kwargs": {},                       # keyword args
    "arg_names": ["order_id"],          # NAMES of the positional args (from the signature)
    "faulted": True,                    # did a fault actually CHANGE this call's return?
    "raised": False,                    # did the fault make the tool throw?
    "result": {"amount": 210.00, ...},  # what the agent ACTUALLY received (post-corruption)
    "pre_fault_result": {"amount": 42.00, ...},   # the REAL value (pre-corruption)
    "is_action": False,
}
```

The quiet-but-heavy fields:
- **`faulted`** is only `True` if the fault genuinely changed something. A no-op corruption records `faulted: False`, so faultline never blames the agent for mishandling a corruption that never happened.
- **`pre_fault_result`** keeps the truth alongside the lie — this pairing lets the cleverest detector (layer 4) catch corruption that got *consumed by math* and never appears literally.
- **`arg_names`** lets the detector reason about *which* argument changed (a harmless `message` vs a consequential `amount`).

### The baseline: a free answer key

faultline has no oracle — it doesn't know the right answer. So how can it tell the agent did wrong? **It runs the agent once with nothing broken first.** That clean run is what a *correct* agent does. faultline keeps it, then every broken run is **diffed against the baseline.** If the agent issued a refund in the broken run it did *not* issue in the baseline, the corruption changed its behavior. The whole detector is built on *faulted run vs. baseline run*.

**The one idea:** wrap tools to get a choke point → record everything into a diary → run once clean for a free answer key → break tools and diff against it.

---

## 2. Every failure type faultline injects

A **fault** is one way reality goes wrong. faultline ships seven (in `faults.py`), in two families:
- **Silent faults** corrupt a tool's *return value* — it still "succeeds," but the data is wrong (the dangerous ones).
- **Hard faults** make the tool *throw* (less dangerous — you'd notice a crash — but worth testing graceful degradation).

Every fault can be aimed (`targets=["get_order"]`) or left to hit every tool. Every fault has `reset()` (called before each trial). Shared rule: **a fault never silently no-ops** (a "corruption" that changes nothing would falsely score the agent as resilient).

### 2.1 `WrongNumber` — "the silent killer"
**Simulates:** a stale cache, unit bug (dollars vs cents), bad join — a *plausibly wrong* number. The headline fault.
**Does:** multiplies every number it finds by a factor (default 5.0), **recursively** through dicts/lists/tuples/pandas, leaving non-numbers alone. Careful: skips booleans; corrupts `Decimal` in Decimal space (money!); never lets `0` stay `0` (uses the factor instead); detects pandas by module name so it stays an optional dep.
**Store example:** `get_order` truly returns `{"amount": 42.00, "delivered_days_ago": 5}`; the agent receives `{"amount": 210.00, "delivered_days_ago": 25}`. Factor can go below 1 too — the battery uses `0.2` to make a 47-day-old order look ~9 days old.

### 2.2 `StaleData` — the cache that never refreshed
**Simulates:** a frozen cache — first call real, every later call replays that first value forever.
**Does:** remembers the first value per tool, replays it on later calls (`reset()` clears it between trials).
**Store example:** stock is 12, a sale drops it to 2, but the second `check_inventory` replays `12`. A robust agent re-checks; a fragile one orders 12 when 2 exist. (Because the first call is real, faultline only marks `faulted` once the cache actually diverges.)

### 2.3 `Truncate` — the half-cut-off response
**Simulates:** a partial page, pagination that stopped early — "I got 3 of 10 and assumed that was all."
**Does:** returns roughly the **first half** — half a string's chars, half a list's items, half a dict's keys; other types unchanged.
**Store example:** `search_kb` returns 3 policy snippets; the critical "never over-refund" one is last; `Truncate` leaves only the first. This is the shape of the real Aider bug (a truncated file read → the model rewrote the file at half length, deleting code).

### 2.4 `NullResponse` — `None` where data should be
**Simulates:** a tool that returns nothing — a dropped connection that still "succeeded."
**Does:** replaces the return with `None`.
**Store example:** `get_order` returns `None`. Does the agent abstain ("couldn't find it, escalating") or crash (`order["amount"]` on `None`) or barrel ahead? A crash is a loud, honest `CRASH`.

### 2.5 `EmptyResult` — the well-formed *empty* payload
**Simulates:** a no-match query, a zero-row result, a rate-limited `200 OK` with an empty body. **Different from `None`:** this is a valid, correctly-shaped *empty* answer, which agents are especially prone to answer from.
**Does:** returns an empty value of the **same shape** — `""`, `b""`, `[]`, `()`, `{}`, an empty set, or `0`. Careful exception: a **named tuple** is left unchanged (it has required fields; emptying to `()` would crash attribute access) — and the doctor flags that as a coverage gap.
**Store example:** "what's your refund window?" → `search_kb` returns `[]`. Does the agent say "I can't confirm right now" (correct) or invent "30 days" from memory (the GPT Researcher silent failure)?

### 2.6 `Timeout` — the tool hangs
**Simulates:** a tool that hangs / times out. **Does:** raises `TimeoutError`. **Store example:** `get_order` throws instead of returning. Graceful retry-with-backoff, or an unhandled crash?

### 2.7 `ServerError` — the tool returns an HTTP error
**Simulates:** a 500/503/429. **Does:** raises `RuntimeError` (status configurable: `ServerError(code=503)`). **Store example:** the "did anyone wrap this in try/except + retry?" fault.

| Fault | Family | What it does | Real cause |
|---|---|---|---|
| `WrongNumber(factor=5.0)` | silent | bends every number recursively | stale cache, unit bug, bad join |
| `StaleData` | silent | replays the first value forever | a cache that never refreshed |
| `Truncate` | silent | returns the first half | partial page / pagination |
| `NullResponse` | silent | returns `None` | dropped connection, hard miss |
| `EmptyResult` | silent | empty value of same shape | no-match query, rate-limited 200 |
| `Timeout` | hard | raises `TimeoutError` | the tool hangs |
| `ServerError(code=500)` | hard | raises `RuntimeError` | HTTP 500/503/429 |

---

## 3. How it decides PASS / SILENT / CRASH

The heart of faultline (`detect.py`, `classify_trial`). Per broken run, one verdict:
- **PASS** — the agent handled it (recovered, abstained, or took no harmful action). Resilient.
- **SILENT** — confidently did the wrong thing on corrupted data, no error. **The dangerous one — the whole point.**
- **CRASH** — threw an unhandled exception. Loud, honest, but still a failure.

It reaches SILENT *without an oracle* by looking for **evidence the corruption flowed into a real decision**, in four layers, checked most-precise first, stopping at the first that fires. Two guards run before the layers:
1. **Did the agent crash?** → `CRASH`.
2. **Did a fault actually reach the agent?** If no event was `faulted`, the agent ran on real data → `PASS` (nothing to judge). This runs *before* invariants, so a fault aimed at an unused tool can never be blamed for a rule break it had no part in.

### Layer 1: Invariant violated (your rules)
*You* write a rule that must always hold; if the broken run breaks it, that's a silent failure. An invariant takes the run record and returns a message-or-`None`. Crucially it checks against **ground truth**, not what the agent saw:

```python
def refund_follows_policy(run):
    for ev in run["events"]:
        if ev.get("is_action") and ev["tool"] == "issue_refund":
            truth = ORDERS.get(order_id)                 # the REAL order
            if truth["delivered_days_ago"] > 30: return "refunded outside the 30-day window"
            if abs(float(amount) - truth["amount"]) > 0.01: return "refunded $%s, true amount $%.2f" % (...)
    return None
```

The gold standard — when you can write one, do. faultline also ships pre-built invariants, each from a real bug: `numeric_answer_finite()` (NaN/inf answers — pandas-ai), `abstain_when_context_empty()` (confident answer from empty retrieval — GPT Researcher), `no_poison_parroting()`, `no_silent_shrink()` (Aider), `tools_really_called()` (section 5).

### Layer 2: Action divergence (the corruption changed what it DID)
If the agent took a consequential action in the broken run it did **not** take in the baseline, the corruption changed its behavior — the strongest no-oracle signal. **Store example:** baseline correctly *declines* the 47-day refund (no action); under `WrongNumber(0.2)` the age 47→9 looks in-window and it fires `issue_refund` — an action in the broken run but not the baseline → SILENT. Two refinements stop false alarms: actions the agent *stops* doing are NOT flagged (doing less may be a safe abstention — left to an invariant); and a *display-only* ride-along (same action + same consequential args, only a `message`/`note`/`log` arg changed to the corrupted value) is suppressed — but **only** when every differing arg is both display-named AND traceable to the injected corruption. Any consequential arg differs, or a non-injected value → flagged. When in doubt, it flags.

### Layer 3: Poison parroting (it repeated the lie as fact)
If a value faultline injected shows up in the agent's answer (but not the baseline's), with no sign of distrust, the agent swallowed the lie. Skips trivial values (None, bools, <2 chars); also compares a thousands-separator-stripped view (so injected `6000` printed `"$6,000"` still matches); checks the **leaves** of nested structures, not the whole `str()`. **The rejection escape hatch (how it stays quiet when the agent does right):** before flagging, it checks `_has_uncertainty` — dict flags like `error`/`rejected`/`unverified`, or rejection *language* ("implausible," "couldn't verify," "refuse," "out of range," "suspicious," "looks wrong"). If present, **not flagged.** A hardened agent that *logs the bad value it refused* must never be punished. This also gates Layer 4.

### Layer 4: Derived-value lockstep (the corruption got eaten by math)
The sneakiest case — the agent never prints the corrupted value, but *uses* it, so only a *derived* number reaches the output. Using the `(real, corrupted)` evidence pairs, faultline lines up numbers in the baseline vs broken output by **structural position** and, for each changed number, checks **three** relationships only: **count** (a resized container's count flowed through — exact match), **ratio** (the corrupt/real factor passed through a multiply), **delta** (the corrupt−real offset passed through an add). A change matching none of the three is **not flagged** (outputs legitimately change for safe reasons — a clamp, a fallback). Hardened against coincidence (drops <2-char evidence; `1e-3` tolerance so rounding doesn't break it) and — same as parroting — **suppressed entirely if the output shows rejection language.** **Store example:** store-credit = `order×0.5`; baseline $42→$21, under ×5 $210→$105; the output never says 210 or 42, but `105/21 == 5.0` (the injected factor) → caught.

### If none fire: PASS
No crash, a fault reached it, no invariant broke, no new harmful action, no parrot, no lockstep → the agent absorbed the fault → PASS. faultline deliberately does **not** flag "the answer text changed" alone (harmless wording changes aren't failures).

### Trials and the aggregate verdict
Each fault runs multiple times (5 in `check`, 3 in `scan`), resetting between trials. Aggregate (`runner.py`): **FAIL** = a true majority SILENT (`silent_count >= trials//2 + 1`) — so it never cries wolf on a one-off; **CRASH** = every trial crashed; **PASS** = every trial passed; **INCONCLUSIVE** = a mix. The per-trial list (`[SILENT, SILENT, PASS]`) shows alongside. **The strict gate:** an intermittent silent failure (2 of 5) aggregates to INCONCLUSIVE, which the report tolerates — but `assert_resilient` is *stricter*: it raises on FAIL, CRASH, **or any single SILENT trial**, because an agent that ships a wrong refund 2 times in 5 is not safe to deploy.

---

## 4. The six modes
All feed the same deterministic detector, so any can gate CI. The first modes feed honest input (a failure is a *real bug*); `chaos` breaks a tool (a failure means "no seatbelt").

- **`scan`** — *"is my agent resilient, with zero setup?"* Discovers wrapped tools, hits each with the full battery, runs the no-oracle detector, no rules needed. `faultline scan agent.py:agent --task '{...}'`. Exits non-zero on a silent failure.
- **`probe`** — *"does my rule hold on weird-but-valid inputs?"* Tests a plain function with edge inputs you supply + properties. No broken tool — the input is the stress test. Caught the chonkie-style "overlap 1.5 → silently 0 chunks."
- **`fuzz`** — *"find the breaking input for me."* `probe` where faultline generates the edge cases (by input type), singly and in pairs; seeded so findings reproduce. How the real chonkie bug was auto-found.
- **`scenarios`** — *"on honest hard cases, does my AGENT break a rule?"* Real, legal, hard situations, no faults — a failure is a genuine agent bug. **Reach for this to find real bugs.** This is what the proof video shows.
- **`replay`** — *"did a model/prompt/version change silently break it?"* `record` today, `replay` after a change, diff the consequential output. Traces persist to disk → a production run becomes a permanent regression test. (`transform=` models context compression.)
- **`mine`** — *"learn the rules from good runs."* Watches a few known-good runs, extracts rules that held across all (tools always called, ordering, output keys), enforces them — catches a refactor that breaks a rule nobody wrote.

*(`chaos` = `fl.check`, the section 2–3 engine. Honest framing: a chaos failure means "no guard," not necessarily "a bug" — its value is comparison. For real bugs, prefer `scenarios`.)*

---

## 5. The extra capabilities
- **`doctor`** — preflight: runs the agent once (no faults) and reports a checklist — Python version, baseline runs clean, which wrapped tools fired (NONE = nothing to break), action tools, and whether each tool's return is **corruptible** (a generator/coroutine/custom object is a coverage gap). Ends `READY`/`NOT READY`. Run it first.
- **`init`** — scaffolds `faultline_suite.py` + a CI workflow (idempotent, never overwrites). The starter agent is intentionally unguarded so `faultline run` catches it out of the box.
- **`scan --explain`** — for each FAIL, prints the evidence: the corruption (`42 → 210`), the resulting action (`issue_refund(..., 210)`), the verdict reasoning. Auditable, not a black box.
- **`faultline.json`** — declarative config (JSON because the engine is zero-dep + 3.9). Fault types are a **closed allowlist** (no arbitrary code); agent/invariants are `file.py:name` refs.
- **`assert_resilient`** — a plain assertion that raises (with the report) on any silent failure; drops into pytest/unittest. Uses the **strict** gate (any single SILENT trial fails). Deliberately not a plugin (a plugin that swallows a failure would be the false-green it sells against).
- **Framework adapters (`instrument`)** — auto-wrap tools inside LangChain (`.func`/`._run`), LangGraph (`ToolNode`), LlamaIndex (`.fn`), pydantic-ai (`.function`), crewAI (`._run`), by the framework's own tool names. Idempotent, transparent outside tests; `actions=[...]` marks the ones to stub. Verified against the real installed libs.
- **`tools_really_called`** — catches a **fabricated tool result**: the agent answered without ever really calling the tool. Deterministic from the real transport log — something an output-only eval can't see. Silent on crash/no-output/honest-abstention. (Catches *missing calls only*, not semantic fabrication; abstention is keyword-detected.)
- **`guard`** — the runtime seatbelt. Same idea in production: a rule checked **before** an action fires. `shadow` (the action still fires, violations recorded) → `enforce` (a violation raises `GuardBlocked`, the real action never runs). Reuses your `fl.wrap(..., is_action=True)`. (A rule that *itself* throws is re-raised in both modes — keep shadow rules exception-safe.)
- **`attest`/`verify`** — `attest` runs the suite (same CI gate) and writes a JSON report with a **SHA-256 content hash** over a canonical, deterministic serialization of the verdicts; `verify` re-derives the hash. Edit a verdict → the hash breaks. **It's a content hash, NOT a crypto signature** — "tamper-evident + reproducible," never "signed"/"tamper-proof"/"certified." The hash covers the verdict body only (not the timestamp/git-SHA/CI-URL meta).

---

## 6. The honest limits (do not soften — this is the credibility)
- **The 97.5% recall / 2.2% false-alarm numbers describe ONE frozen 85-case pure-Python benchmark.** Never attach them to any LLM-agent, framework, or new-detector claim.
- **scan blind spots:** it catches the *harmful-action* direction, not *does-nothing* (an over-read that makes the agent order nothing needs an invariant). Text-shape guarantees need an invariant.
- **Uncorruptible return types (coverage gap):** value faults reach dict/list/tuple/str/bytes/number/set (+ pandas). A **generator, coroutine, dataclass, or pydantic model** is passed through uncorrupted → the trial is a coverage gap, **not** an all-clear (scan/doctor print a note). Workaround: materialize (`list(stream())`) or assert an invariant.
- **Two known false positives:** a *safe-fallback constant* that coincidentally matches the lockstep math; a *fail-safe escalation* (a new SAFE action like `alert_ops`) read as a divergent action. Disambiguate with an invariant.
- **Async is sync-only but fails LOUD:** an async agent gets a clear error + the `asyncio.run(...)` workaround (not a silent coroutine pass). An async tool is uncorruptible (same coverage gap).
- **Concurrency:** per-thread isolated for fresh/stateless faults (safe for CI parallelism). A single **stateful** fault instance (one `StaleData()`) **shared across threads** races — use a fresh instance per concurrent run.
- **Trace log records args/result by reference:** if your agent mutates an argument *after* the call, an invariant reading `event["args"]` sees post-mutation state (a possible false PASS) — read the output/decision, not mutated inputs. Also: a real tool that throws its *own* exception (no fault active) isn't recorded as an event.
- **`tools_really_called` catches missing calls only** (not semantic fabrication); abstention is keyword-detected and incomplete.
- **`guard` shadow isn't perfectly inert:** a rule that *raises* is re-raised even in shadow — keep shadow rules exception-safe.
- **The wild catches:** 5 PRs open, 1 closed (LangChain #37964, closed by a repo bot — never a "win"). The Haystack/LlamaIndex `hunts/` items are *demonstrations on real library code*, not "bugs found in X." The LangGraph end-to-end example uses a **deterministic stand-in model** — never imply a live LLM produced that catch.
- **Traction:** zero outside users until proven otherwise. No implied users/stars/adoption.

**That's the whole engine.** One trick — wrap tools, record into a diary, run once clean for a free answer key, break tools and diff. Seven faults. A four-layer detector that catches the silent-wrong without an oracle and stays quiet when the agent does right. Six modes. A handful of supporting tools. And a hard, honest line around what it does *not* catch — because a tool that finds silent failures must never have one.
