# Changelog

All notable changes to faultline. Dates are when the work landed.

## 0.4.2 — 2026-06-11

Integration + adoption release. Everything is **additive** — the 85-case benchmark numbers
(97.5% recall / 2.2% false-alarm, deterministic-Python) are unchanged; the existing detector
layers were not touched.

### Added
- **`faultline scan` (zero-config)** — point it at your agent (`FILE.py:agent`), no suite file and no
  hand-written invariants: it auto-discovers your wrapped tools, hits them with the default fault
  battery, runs the built-in detector, and gates CI. `fl.scan(agent, task)` API + `faultline scan` CLI.
- **`fl.assert_resilient(agent, task, ...)`** — a drop-in pytest/unittest assertion that raises (with the
  full report) on any silent failure. Import-light, fails loud. `faults=None` uses the scan battery.
- **Framework adapters** — `fl.instrument()` (universal, idempotent) and `fl.instrument_langgraph()` wrap
  the **real tool seam** (LangGraph `ToolNode` / compiled `create_react_agent`, LangChain `StructuredTool`,
  LlamaIndex `FunctionTool`) so an injected fault genuinely reaches the tool. Verified against the real
  installed libraries (langgraph 1.x, langchain 1.4.x, llama-index 0.14).
- **`fl.tools_really_called(tools)`** — deterministic **fabrication detector**: catches an agent that
  produces a confident answer from a tool result it never actually fetched, by inspecting the real
  transport log (something an output-only eval/LLM-judge can't see). Silent on honest abstention, crash,
  or a real call.
- **`fl.EmptyResult`** — a fault returning a well-formed-but-empty payload (`""` / `[]` / `{}` / `0`),
  distinct from `NullResponse` (`None`). Added to the scan battery.
- **`replay(transform=...)`** — behavioral-drift detector: apply a context compression / rotation / prompt
  change to a recorded trace and diff the agent's behavior (the "silently changed after compression" class).
- **`fl.DEFAULT_ABSTAIN_MARKERS`** exported for tuning the fabrication detector's abstention list.
- End-to-end example: a deterministic, key-free catch on a real `create_react_agent`
  (`faultline/examples/langgraph_catch.py`); a scan-able example agent (`faultline/examples/your_agent.py`).

### Changed
- **CI** now runs the full suite (`tests/run_all.py`) on every Python leg and installs
  langgraph/langchain-core on 3.10+, so the real-library adapter suites actually execute.
- README + MODES.md document all of the above.

### Notes
- `ArgDrop` (a fault that corrupts a tool's *inbound* args) was scoped in but deferred — it needs a new
  mutation seam in the core wrapper and is better landed with a human at the integration gate.
- Python 3.9 compatible (`from __future__ import annotations`; no `X | Y` unions, no `match`). The
  framework-adapter test suites skip cleanly on 3.9 and run against the real libs on 3.10+.

## 0.4.1
- Runtime guard (`fl.guard`, shadow/enforce) and tamper-evident attestation (`faultline attest`/`verify`).
