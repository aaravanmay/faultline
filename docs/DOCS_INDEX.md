# faultline — project map (where everything lives)

**faultline** = chaos engineering for AI agents: break an agent's tools on purpose (wrong /
stale / empty / truncated data, timeouts, 500s) and catch where it *silently does the wrong
thing* — a confident wrong answer with no error. Deterministic detection, runs in CI.

**Status:** engine + invariant library built & tested; **proven by finding 17 real silent-failure
bugs in 16 famous open-source agents** (2 PRs filed, 15 staged & verified). See
[`../MORNING_SUMMARY.md`](../MORNING_SUMMARY.md) for the file-each checklist.

---

## Map (after the Jun 8 reorg)

### Root — entry points
- [`../README.md`](../README.md) — public OSS readme (leads with the 17-bug proof).
- [`../MORNING_SUMMARY.md`](../MORNING_SUMMARY.md) — **read first:** the staged-PR file-each checklist.
- [`../FINDINGS.md`](../FINDINGS.md) — live evidence narrative (custom Claude, LangChain, smolagents).
- [`../CLAUDE.md`](../CLAUDE.md) — project rules + conventions. `LICENSE`, `pyproject.toml`, `action.yml`.

### The code
- `../faultline/` — the Python package. **`invariants.py` = the moat** (4 reusable deterministic
  invariants distilled from the real bugs). `faults.py` (fault library), `detect.py` (no-oracle
  classifier), `runner.py` (`check()`), `trace.py` (`tool`/`wrap`), `cli.py` (`faultline` command),
  `legacy.py` (v0.1 oracle).
- `../tests/` — `smoke_test.py` (8/8), `test_invariants.py` (16/16), `test_v1.py`.
- `../examples/` — `demo_silent_rag.py` (runnable demo, no keys), `quickstart.py`.
- `../bench/` — **the 17 PR packages** (`pr_<name>/PR.md` = title + body + verified test for each bug).
- `../evidence/wild_catches/` — the evidence table of all catches + per-bug write-ups.
- `../site/` — the marketing website (`index.html`, `index-redesign.html`).

### docs/ (you are here)
- `strategy/` — [CONCEPT_AND_EXECUTION.md](strategy/CONCEPT_AND_EXECUTION.md) (start here for the full
  story), [PRODUCT.md](strategy/PRODUCT.md), [V1_SPEC.md](strategy/V1_SPEC.md),
  [HUNT.md](strategy/HUNT.md), [PLATFORM_GUIDE.md](strategy/PLATFORM_GUIDE.md) (+ `.html`).
- `launch/` — [LAUNCH_POST.md](launch/LAUNCH_POST.md) (Show HN drafts),
  [RECORDING_SCRIPT.md](launch/RECORDING_SCRIPT.md) (60-sec demo),
  [What_I_Built.html](launch/What_I_Built.html) (the dad write-up), [LOGO_DRAFTS.html](launch/LOGO_DRAFTS.html).
- [OVERNIGHT_HUNT_LOG.md](OVERNIGHT_HUNT_LOG.md) — the full bug-hunt run log + backlog (ragflow, swarms,
  MetaGPT, crewAI). `faultline-report.md`, `tripwire-report.md` — sample generated reports.

### Sibling: the PR fork clones
- `../../faultline-forks/` — the 18 local clones of the OSS repos we patched (one per bug), each a
  pushed `aaravanmay` fork. See its `README.md` for the fork → branch → status table.

### Scratch / history (ignore day-to-day)
- `../junk/` — disposable screenshots & temp scripts (safe to delete). `../archive/` — old process docs.

---

## New here? Read in this order
1. `docs/strategy/CONCEPT_AND_EXECUTION.md` — what it is, in plain language.
2. `../README.md` — the proof + how to use it.
3. `../MORNING_SUMMARY.md` — the 17 bugs and how to file the staged PRs.
4. `docs/strategy/PRODUCT.md` — positioning, moat, pricing, risks.
