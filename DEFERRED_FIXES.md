# Deferred fixes — attended-block backlog

Everything here was found by the overnight adversarial passes and **deliberately not fixed unattended**
because each touches the core wrapper or a recall/precision tradeoff (a wrong call would regress the moat).
Each is disclosed in CAPABILITIES.md. This file makes them quick to land with a human at the gate.
Discipline for all of them: **re-run the full 85-case benchmark before/after; zero regression or revert.**

Ranked by value × (inverse) risk.

## 1. trace.py records args/result by REFERENCE (HIGH — defeats the flagship invariant pattern)
- **Bug:** `faultline/trace.py` shallow-copies args/kwargs/result into the event. If the agent mutates an
  argument *after* the call (`place_order(cart)` then `cart.clear()`), an invariant reading `event["args"]`
  sees post-mutation state → a real oversell reads as a false PASS. This is exactly the "compare what the
  agent saw vs what it did" pattern scenarios.py sells.
- **Repro:** an agent that orders 4 with 3 in stock then clears the cart → `no_oversell` reads len 0 → PASS.
- **Fix:** deep-copy args/kwargs/result at capture, with a safe fallback (try `copy.deepcopy`; on failure —
  generators, locks, db handles — fall back to a `repr` snapshot or the shallow copy + mark
  `uncopyable=True`). Cost: a deepcopy per wrapped call (acceptable; it's a test tool, not the hot path).
- **Risk:** core wrapper — every call + recorded event flows through it. Uncopyable objects must not crash.
  Test the full suite + benchmark + the identity tests (None/0/""/generator) after.
- **Unblocks:** the flagship action-agent invariant pattern becomes trustworthy under arg-mutation.

## 2. trace.py — a tool's OWN exception isn't recorded as an event (MED)
- **Bug:** when no fault is active and the tool itself raises, the exception escapes before the event is
  appended → `run["events"]` has no record of the call. (An *injected* raise DOES record.)
- **Fix:** wrap the real call so the event (with `raised=True` + the exception) is appended before
  re-raising — symmetric with the injected-fault path.
- **Risk:** core wrapper; same blast radius as #1. Land them together.

## 3. EmptyResult / value faults no-op on generators / coroutines / custom objects / dataclass / pydantic (MED)
- **Bug:** value-corruption faults only reach dict/list/tuple/str/number (+ pandas for WrongNumber). A tool
  returning a generator (streaming), coroutine, dataclass, pydantic model, or namedtuple is passed through
  uncorrupted → the trial reads "fault never reached" → a coverage gap that looks like a PASS.
- **Fix:** (a) for the faults, add handlers (materialize+empty a generator; zero pydantic/dataclass numeric
  fields). (b) Better: detect "value-corruption fault applied but return type is uncorruptible" and surface
  it as an explicit COVERAGE-GAP status in the report (distinct from PASS), so it can never read as resilience.
- **Risk:** (b) is a report/verdict-display change (moderate); (a) touches faults.py per-type (contained).

## 4. Detector false positive — derived-value lockstep collides with a safe-fallback constant (MED)
- **Bug:** a hardened agent that rejects bad data and returns a fixed constant (eta=405) is flagged FAIL when
  that constant happens to differ from baseline (5) by exactly the injected delta (+400).
- **Fix:** require corroborating evidence before the derived-value layer fires on a single pair (e.g. the
  moved number must also appear in / derive from the corrupted value, not just share its offset), or down-weight
  delta-only matches. **Must not drop recall** — gate on the full benchmark.
- **Risk:** detector precision change — the dangerous direction. Attended + benchmark-gated only.

## 5. Detector false positive — fail-safe escalation action flagged as harmful (LOW-MED)
- **Bug:** an agent that, on implausible data, pivots to a new SAFE action (`alert_ops(...)`) is flagged as a
  divergent harmful action; the detector can't tell a harmful action from a safe escalation.
- **Fix:** hard problem — needs a signal for "harmful vs safe-escalation" (an allowlist of safe actions, or
  letting the user tag actions). Likely a small API addition, not a pure detector change.

## 6. ArgDrop fault (FEATURE, deferred from the planned blocks)
- A fault that corrupts a tool's *inbound* args (drops/blanks one) needs a new inbound-arg mutation seam in
  trace.py's wrapper (every existing fault only transforms the *result*). Land with #1/#2 (same wrapper).

## 6b. Native async support (FEATURE, deferred)
- **Gap:** faultline is sync-only. An async agent now fails loud with a workaround (good), but native
  support — `await`-ing an async agent + corrupting an async tool's awaited value — needs an async path in
  `run_once` + the wrapper (detect coroutine, await it inside the session, corrupt the result). Core-wrapper.
- **Fix:** an `async_run_once` / make `run_once` await coroutine returns under a managed loop; the wrapper
  awaits a coroutine tool result before handing it to `fault.hit`. Land with the #1/#2 wrapper pass.

## 6c. Stateful faults aren't thread-safe to SHARE across threads (LOW — niche)
- **Gap:** `StaleData._seen` (and any future stateful fault) is a plain instance dict. One fault instance
  shared across concurrent threads races (proven: 400/600 cross-contaminated). The normal pattern (a fresh
  fault per run) is safe; only sharing a stateful instance is not.
- **Fix:** back stateful caches with `threading.local()` (per-thread `_seen`), reset clears the current
  thread's. Contained to faults.py. Low priority — outside the documented usage.

## 7. guard shadow re-raises on a rule EXCEPTION (DESIGN DECISION — not clearly a bug)
- A rule that itself raises aborts the action even in shadow. Deliberate ("a crashing rule is a bug, not a
  violation to log") but it means a buggy rule can affect production in shadow. **Founder call:** keep as-is
  (documented), or catch in shadow → record + let the action fire (only hard-fail in enforce).
