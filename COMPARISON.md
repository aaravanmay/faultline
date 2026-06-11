# faultline vs. evals, LLM-judges, and guardrails

The first question reviewers ask is "how is this not just evals?" Short answer: **evals and judges grade
the agent's output on data you give it. faultline breaks the agent's *tools* and checks what it does with
bad data — deterministically, no second LLM.** They're complementary; faultline catches a failure class
the others structurally can't see.

## The failure faultline targets
An agent doesn't crash. A tool returns a confident, wrong value — stale inventory, an empty retrieval, a
truncated list — with a 200 OK. The model reasons correctly *over the bad input* and ships the wrong action.
Your eval, which runs the agent on **clean** data, passes it. That "200-OK-but-wrong" gap is the wedge.

## Capability matrix

| Can it catch… | **faultline** | Evals (DeepEval / Braintrust / promptfoo) | LLM-as-judge | Guardrails (Guardrails AI / NeMo) | Tracing (Langfuse / LangSmith) |
|---|:---:|:---:|:---:|:---:|:---:|
| A wrong answer on **clean** data (with labels) | ➖ | ✅ | ✅ | ➖ | ➖ |
| **200-OK-but-wrong**: agent acts on a tool's bad return | ✅ | ❌ (doesn't break tools) | ❌ | ❌ | ❌ |
| **Resilience** to tool faults (wrong / stale / empty / timeout) | ✅ | ❌ | ❌ | ❌ | ❌ |
| **Fabricated tool result** (answered from a tool never called) | ✅ (transport log) | ❌ (output-only) | ❌ | ❌ | ➖ (you'd read traces by hand) |
| **Behavioral drift** after a context/prompt change | ✅ (`replay`) | ➖ (re-run, no behavior diff) | ➖ | ❌ | ➖ |
| **Deterministic** verdict (same input → same result) | ✅ | ✅ | ❌ (LLM variance) | ✅ | n/a |
| Needs **no second LLM** / no judge API cost | ✅ | ➖ | ❌ | ✅ | n/a |
| Input/output **schema validation** | ❌ | ➖ | ➖ | ✅ | ❌ |
| **Runtime** blocking in production | ✅ (`guard`) | ❌ | ➖ | ✅ | ❌ |
| Record / inspect runs | ➖ (records, not a platform) | ➖ | ❌ | ❌ | ✅ |

✅ core strength · ➖ partial / not the focus · ❌ structurally can't

## Why a deterministic detector, not an LLM judge
An LLM judge grading "is this answer right?" is itself non-deterministic and can't see *process* — whether a
tool was actually called, whether the agent acted on corrupted data. faultline owns the real call log, so
"a tool was answered-from but never called" or "the agent ordered 900 when the tool was corrupted to 900"
is a **recorded fact**, not an inference. That makes verdicts reproducible and CI-gateable. (Scope + the
exact benchmark for the detector are in [CAPABILITIES.md](CAPABILITIES.md); the 85-case figures there are a
deterministic-Python benchmark, not a claim about LLM agents.)

**See it yourself:** `python3 examples/vs_eval.py` runs one agent two ways — a plain eval goes green on clean data, then faultline breaks the retrieval tool and catches the same agent fabricating an answer. The gap, executable.

## faultline complements your evals — it doesn't replace them
- **Evals** tell you the agent is right on the cases you thought of. Keep them.
- **Guardrails** validate shape and block bad I/O at runtime. Keep them.
- **Tracing** shows you what happened after the fact. Keep it.
- **faultline** answers a question none of them do: *when a tool silently returns bad data, does the agent
  do the wrong thing — and would anything have caught it?* Run it in CI alongside your evals.

## Honest limits
faultline is strongest on **action-taking and numeric** agents (a wrong action has a price tag). It is not a
general correctness oracle, not a security/jailbreak red-teamer, and its zero-oracle detector has documented
blind spots and two known false-positive classes ([CAPABILITIES.md](CAPABILITIES.md)). It finds a specific,
expensive, under-covered failure — not every failure.
