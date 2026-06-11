# What faultline catches — and what it doesn't

The honest, per-feature scope. Read this before writing any launch post, README claim, or reply — each
entry gives **what it catches**, its **known blind spot**, and the **one wording rule** that keeps the
claim true. The whole project's credibility rests on never overclaiming; this file is the guardrail.

## The one rule above all
The **97.5% recall / 2.2% false-alarm** benchmark numbers are from an 85-case, **deterministic-Python**
suite (`benchmark/MEASUREMENT.md`). Never attach them to anything involving an LLM agent, a framework
adapter, or a new detector. They describe one frozen benchmark; everything else is described separately.

---

## scan (zero-config)
- **Catches:** an agent that takes a harmful/divergent action, crashes, or parrots a corrupted value, when
  its tools are broken — with no invariant written. Strongest on **action-taking and numeric** agents.
- **Blind spot:** the zero-oracle layers catch the *harmful-action* direction. A corruption that makes the
  agent do **less / nothing** (e.g. an over-reading inventory → orders nothing) does not diverge an action,
  so scan can miss it — that case needs an invariant. Text-shape guarantees also need an invariant.
- **Blind spot — uncorruptible return types (important).** The value-corruption faults
  (`WrongNumber`/`StaleData`/`Truncate`/`EmptyResult`) reach **dict / list / tuple / str / number** (and
  `WrongNumber` reaches pandas). A tool that returns a **generator / iterator (streaming), a coroutine, or
  a custom object / dataclass / pydantic model** is passed through *uncorrupted* — so the fault shows as
  "never reached" and the trial is a **coverage gap, not proof of resilience**. `scan` prints a note when
  this happens; do not read it as an all-clear. Workaround today: materialize such returns
  (`list(stream())`) at the wrapped boundary, or assert an invariant. (Corrupting lazy/opaque returns
  in-place is a core-wrapper change deferred to an attended release.)
- **Known false positives (adversarial-found, fix deferred).** Two cases where the no-oracle layers can
  FLAG A CORRECT agent — use an invariant to disambiguate if you hit them: (a) a *safe-fallback constant*
  that happens to differ from the baseline number by exactly the injected delta/factor is read as a
  derived-value lockstep (e.g. an agent that rejects bad data and returns a fixed `eta=405` while baseline
  was `5`, under a +400 corruption); (b) a *fail-safe escalation* — an agent that, on implausible data,
  takes a new SAFE action (e.g. `alert_ops(...)`) instead of acting — is flagged as a divergent action,
  because the detector can't tell a harmful action from a safe escalation. Fixing these without losing
  recall is a detector change deferred to an attended block. (The thousands-separator FN they also found
  *was* fixed — benchmark-gated, zero regression.)
- **Wording:** "zero-config first look" / "catches with no rules written." NOT "catches every silent failure."

## fl.assert_resilient
- **Catches:** same as scan/check — raises on any SILENT or CRASH verdict.
- **Blind spot:** inherits scan's blind spot. With `faults=None` it needs your tools wrapped (it says so loudly).
- **Wording:** "a drop-in assertion." It is NOT a pytest plugin (deliberately — a plugin that swallows a
  failure would be the false-green it sells against).

## instrument / instrument_langgraph / _langchain / _llamaindex
- **Catches:** nothing by itself — it *wires* faults into a framework agent's real tools so check/scan can.
- **Verified:** against real installed **langgraph 1.x, langchain 1.4.x, llama-index 0.14** (fail-first
  tests: a fault provably does NOT reach the tool before instrument, and DOES after).
- **Blind spot:** wraps the tool callable seam (`.func` / `_fn` / `ToolNode.tools_by_name`). A framework
  version that routes tool execution through a different attribute would need a re-verify (the tests catch
  that — they go red, not vacuously green).
- **Wording:** "verified against the real installed library." NOT "works with every version of every framework."

## langgraph_catch.py (the end-to-end example)
- **Shows:** a REAL `create_react_agent` graph (real ToolNode, real tool execution) placing a wrong order
  off a corrupted inventory reading — caught SILENT, deterministically.
- **Blind spot / the qualifier that MUST stay:** the model is a **deterministic stand-in** (scripted, so it
  reproduces and needs no API key). The graph/tools are real; the *model* is not a live LLM. The live-LLM
  catch is `examples/llm_agent_proof.py` (§7.1) only. And the catch is asymmetric: under-reading is caught
  zero-oracle, over-reading needs an invariant.
- **Wording:** "faultline catches a real create_react_agent (deterministic stand-in model)." NEVER imply a
  live LLM produced this catch.

## tools_really_called (fabrication detector)
- **Catches:** an agent that produces a confident answer **without ever calling** a tool it should have —
  i.e. it fabricated/hallucinated the tool result. Deterministic, from the real transport log (a fact, not
  an inference) — which an output-only eval or LLM-judge cannot see. That last point is the real moat.
- **Blind spot:** **missing-call only.** It does NOT catch *semantic* fabrication (the tool WAS called but
  the agent lied about the result). And abstention is **keyword-detected** and incomplete — a prose
  abstention the markers miss ("no hits", "nothing to report") false-positives until you pass it via
  `abstain_markers=`.
- **Wording:** "catches a tool result the agent answered from but never actually fetched." NOT "catches all
  fabrication / hallucination." Keep the "confident, non-abstaining" qualifier; never imply zero false-positives.

## EmptyResult / the fault library
- **Catches:** nothing alone — it's a fault that returns a well-formed-but-empty payload (`""`/`[]`/`{}`/`0`,
  distinct from `NullResponse`'s `None`), so you can test how an agent handles a 200-OK-but-empty tool result.
- **Wording:** "a fault that simulates an empty tool response."

## replay(transform=) (drift)
- **Catches:** an agent whose decision silently changes after a context compression / rotation / prompt
  change — by diffing the replayed behavior against the recording.
- **Blind spot / hard rule:** the transform MUST be pure and deterministic (no time/RNG/ordering) or the
  same run verifies differently and breaks attest/verify. And it must model a real change to the agent's
  input — never feed the agent data the live agent never saw (that's replay oracle-seeding → a fake regression).
- **Wording:** "catches behavioral drift after a context change you apply."

## attest / verify (Rung 3 — tamper-evidence)
- **Catches:** any edit to a report's **verdict content** (a flipped FAIL→PASS, a changed count, a mutated
  finding) — the content hash breaks. Verified non-forgeable under adversarial attack (type coercion, list
  reorder, key injection, whitespace mangling all caught), and a clean report survives a load→save→verify
  round-trip without falsely reading tampered.
- **Blind spot / wording:** the hash covers the **verdict body only** — NOT the `meta` (timestamp, git SHA,
  CI URL, version) or the `attestation` provenance block. "Verified" means *these verdicts are exactly what
  faultline produced and weren't edited* — NOT *this run happened at this time / commit / CI job*. Say
  "attests the verdicts," never "attests the run's provenance." (And it's a content hash, not a crypto
  signature — never say "cryptographically signed.")

## The wild-catches / PRs
- **5 PRs open, 1 closed** (LangChain #37964, closed by a repo bot — never call it a win). The
  `evidence/wild_catches/` Haystack item is a **demonstration** ("faultline's invariant fires on a real
  Haystack pipeline fed an empty-retrieval shape"), NOT "a bug found in Haystack." Keep that distinction.
- **Wording:** "filed PRs from real catches" (with current open/closed status) and "demonstrations on real
  library code" — never blend the two, never inflate the count.

## Traction
- Zero outside users until proven otherwise. No launch asset may imply users, stars, or adoption that don't exist.
