# faultline benchmark — measurement report

**Date:** 2026-06-09 · **Rows:** 85 · **Verdict source:** `results.json` in this directory (every row, every note, including the ones that make us look bad).

This document is the honest record of what faultline's detector actually does on a benchmark we built ourselves. The same org built the tool and the benchmark. An independent audit re-ran everything and overturned zero labels, but you should still read section 6 before trusting anything in section 1.

---

## 1. Headline numbers

Verdict: **faultline catches most injected bugs and never misses when you give it an invariant — but the invariants in this benchmark were written knowing where the faults were, and the no-oracle layers have real, named blind spots and a real false-alarm problem.**

| Metric | Overall (n=85) | With invariant (n=38) | No invariant (n=47) |
|---|---|---|---|
| **Recall** (bugs caught) | **87.5%** (35/40) | **100%** (20/20) | **75.0%** (15/20) |
| **False-positive rate** (safe rows flagged) | **15.6%** (7/45) | 16.7% (3/18) | 14.8% (4/27) |
| **Precision** (flags that were real bugs) | **83.3%** (35/42) | 87.0% (20/23) | 78.9% (15/19) |
| **Determinism** (identical verdicts across 2 runs) | **100%** (85/85) | 100% | 100% |
| Crashes / inconclusive | 0 / 0 | 0 / 0 | 0 / 0 |

The split is the honest story. **With invariants** is the recommended usage: you write a rule about what your agent's output must look like, and in this benchmark that condition missed nothing. **No invariant** is the floor: what faultline catches with zero configuration, using only its built-in action-divergence and parroting layers. That floor is 75% here — and on the real-project cases specifically, the no-oracle floor was **2 of 5 bugs (40%)**. That number is in this report on purpose.

Three caveats before you quote anything:

1. **4 of the 7 false positives are one detector bug**: the parroting layer cannot tell "agent echoed the bad value while *rejecting* it" from "agent believed the bad value." It currently penalizes agents for good logging practice.
2. **The 100% with-invariant recall is partly self-fulfilling.** The benchmark author wrote the invariants knowing what the faults were. The audit flagged two invariants as oracle-seeded and one (RW-11) as not fault-discriminating at all — it fires on honest data too. Details in sections 4 and 6.
3. **Every agent in this run is deterministic Python.** No LLM-driven agents were tested. Do not extrapolate these rates to LLM agents.

---

## 1.5 UPDATE (same day) — after detector fixes, same benchmark re-run

The two dominant failure modes in §4 were fixed in the detector (NOT in the benchmark — the
85 case files are byte-identical; only `faultline/trace.py`, `detect.py`, `invariants.py` changed):

1. **Rejection-echo** — an agent that echoes a bad value while *rejecting* it ("implausible",
   "refused", abstention) is no longer flagged as parroting. Good logging is no longer punished.
2. **Leaf-level parroting** — corrupted values are now matched per scalar *inside* dict/list
   tool payloads, instead of comparing the str() of the whole container. This was the real-world
   blind spot (gap_pct extracted from a quote dict, stop-loss inside a sizing dict).
3. **Faulted-only-if-changed** — a tool call is only marked "faulted" when the fault actually
   altered the value (StaleData's first call and WrongNumber on number-free data no longer
   produce phantom corruption).

Same 85 rows, same ground truths, full suite (71 unit tests) still green:

| Metric | Before | **After** |
|---|---|---|
| Recall (overall) | 87.5% (35/40) | **92.5% (37/40)** |
| False-positive rate (overall) | 15.6% (7/45) | **4.4% (2/45)** |
| Precision | 83.3% | **94.9%** |
| Recall, no invariant (zero-config) | 75.0% (15/20) | **85.0% (17/20)** |
| FP rate, no invariant | 14.8% | **3.7%** |
| **Real-project bugs, zero-config** | **40% (2/5)** | **80% (4/5)** |
| Determinism | 100% | **100%** |

## 1.6 UPDATE (Wave 3) — derived-value + display-arg detector upgrades, same benchmark re-run

Three more gaps from the §4 inventory closed — again in the DETECTOR, not the benchmark (the 85 case files are byte-identical; only `faultline/trace.py`, `detect.py`, `faults.py`, `fuzz.py` changed):

1. **Display-only action args (false-positive fix).** When a fault corrupts only a non-consequential / free-text argument of an action (a log line, a `message`) while the action and its consequential args are unchanged, it is no longer flagged as action divergence. The tool wrapper now records each call's positional arg *names* (via `inspect.signature`), so the detector tells a corrupted `qty` (consequential) from a corrupted `message` (display-only). Conservative: when arg roles can't be determined, it still flags — recall stays the priority.
2. **Derived-value blind spot (false-negative fix).** When an agent consumes the corrupted value through arithmetic / count transforms (a sum, a count, `x*price`, rounding) the injected number never appears verbatim, so leaf-parroting missed it. The wrapper now keeps the REAL pre-corruption value alongside the corrupted one, and the detector flags when a numeric in the faulted output diverges from the baseline output in a way traceable to the corruption. Deterministic and bounded — no LLM judge, no combinatorial search.
3. **Capability adds (no benchmark row exercises them yet).** `WrongNumber` now bends numeric columns of pandas DataFrames/Series (optional dependency, feature-detected, returns a copy — never mutates the caller's frame); `fuzz` auto-generates dict edge cases (empty, key-dropped, None-valued, nested-bent, extra key). Covered by the 29 new Wave-3 unit tests.

Same 85 rows, same frozen ground truths, full suite (95 + 29 Wave-3 tests) green, re-run twice → identical verdicts:

| Metric | §1.5 | **Wave 3** |
|---|---|---|
| Recall (overall) | 92.5% (37/40) | **97.5% (39/40)** |
| False-positive rate (overall) | 4.4% (2/45) | **2.2% (1/45)** |
| Precision | 94.9% | **97.5%** |
| Determinism | 100% | **100%** |

Three cases flipped, **all toward ground truth**:
- `action_agents-09-noinv` FAIL→PASS — the display-only-arg false positive, now correctly SAFE.
- `fn_traps-07-noinv` PASS→FAIL — tax computed from a 5× income, only the derived tax in the output: now caught.
- `fn_traps-08-noinv` PASS→FAIL — count of a silently-halved list reported as the full count: now caught.

Remaining, stated honestly: **1 FN** — `real_world-12`, an EV figure where the corrupted cohort price fully dissolves into a ratio so no traceable numeric survives in the output; still missed with no invariant (an invariant catches it). **1 FP** remains. No benchmark case was edited to produce these numbers.

Remaining failures, all named:
- **FP ×2:** `action_agents-09-noinv` (a corrupted *display-only* action arg changes the action
  signature — needs a way to mark args non-consequential; structural, future feature) and
  `fp_traps-07a-inv` (a deliberately sloppy user-written rule firing on date digits — measures
  user error by design, not the detector).
- **FN ×3:** `fn_traps-07/08-noinv` and `real_world-12-noinv` — the corrupted value is consumed
  in arithmetic / reduced to a count, so nothing corrupted ever appears in output or action args.
  This is the honest residual blind spot of zero-config mode; a one-line invariant catches each.

Per-row data: `results_after_fixes.json`. The §1/§3/§4 numbers below are the ORIGINAL
(pre-fix) run, preserved as the honest "before".

---

## 2. What was measured and how

**The tool.** faultline injects faults into an agent's tool calls (wrong-number ×5 or ×0.1, null-response, stale-data, truncate), runs the agent on clean data (baseline) and corrupted data (faulted), and reports FAIL if any of three detection layers fires:

1. **Invariant** — a user-written rule about the output (e.g. "shares ordered must be ≤ 100").
2. **Action-divergence** — the faulted run takes an action (tool call marked `is_action`) that the baseline did not, or with different args. Stopped actions (agent abstains under fault) deliberately do NOT fire this layer.
3. **Parroting** — the corrupted value appears verbatim in the faulted output but not in the baseline output, without an uncertainty hedge.

A FAIL means "this agent silently does something different/wrong when its data is corrupted." A PASS means "the agent handled the fault: recovered, abstained, or its behavior didn't change."

**The benchmark.** 85 rows across 5 families, each row = one (agent, fault, condition) triple:

| Family | n | What it tests |
|---|---|---|
| `numeric_decisions` | 18 | Trading-style toy agents (breakout signal, position sizer, price-target scorer), buggy and hardened variants |
| `action_agents` | 18 | Agents that take irreversible actions (orders, refunds, shipping, deletes, alerts) |
| `fp_traps` | 16 | **All-SAFE adversarial rows** engineered to bait the detector into false alarms (clamping, hedged echoes, display-only values, constant tools, cross-checking agents) |
| `fn_traps` | 16 | **All-BUG adversarial rows** engineered to slip past the no-oracle layers (transformed values, opaque-ID actions) |
| `real_world` | 17 | Agent logic ported from three real projects of ours: trading gap-and-go + position sizing (Finance project), an investing revision-scorer, and a dd-research EV calculator + flip scanner |

**Ground truth** was labeled by directly executing each agent with and without the fault **before** running the detector — the label records what the agent actually does (harmful action vs safe handling), not what the detector says. One label was corrected when direct execution contradicted the original design (`action_agents-07`: StaleData on a single-call tool has no effect, so GT was corrected BUG→SAFE; the correction is recorded in the row notes).

**Verification.** Every family was re-run independently; all 85 verdicts matched (determinism 100%). A separate audit pass re-checked every ground-truth label against the code and hunted for rigging patterns (invariants tailored to fault values, back-filled verdicts, crashes counted as catches). Results:

| Family | Audit verdict | Re-run matched | Labels overturned | Rigging found |
|---|---|---|---|---|
| numeric_decisions | minor-issues | yes | 0 | none |
| action_agents | minor-issues | yes | 0 | none |
| fp_traps | minor-issues | yes | 0 | none |
| fn_traps | minor-issues | yes | 0 | **3 issues, none verdict-altering** (post-hoc gt_basis notes, family name overstates scope, 2 oracle-seeded invariants — see §6) |
| real_world | minor-issues | yes | 0 | **1 mis-calibrated invariant** (RW-11 fires on honest data too — see §4 and §6) |

No family was excluded from the results.

---

## 3. Confusion matrices

Convention: BUG = a fault makes the agent silently do something harmful; SAFE = the agent handles the fault. Flagged = faultline said FAIL.

A note on crashes: if a fault makes the agent **crash**, that is a *loud* failure — your tests and logs see it without faultline's help. faultline's job is the *silent* failures. Crashes are therefore tracked separately, and this run had **zero** crashes on both bug and safe rows, and zero inconclusive rows. Nothing was quietly dropped into a convenient bucket.

**Overall (n=85):**

| | Flagged (FAIL) | Not flagged (PASS) |
|---|---|---|
| **BUG (40)** | TP = 35 | FN = 5 |
| **SAFE (45)** | FP = 7 | TN = 38 |

**With invariant (n=38):**

| | Flagged | Not flagged |
|---|---|---|
| **BUG (20)** | TP = 20 | FN = 0 |
| **SAFE (18)** | FP = 3 | TN = 15 |

**No invariant (n=47):**

| | Flagged | Not flagged |
|---|---|---|
| **BUG (20)** | TP = 15 | FN = 5 |
| **SAFE (27)** | FP = 4 | TN = 23 |

**Per family:**

| Family | n | TP | FN | FP | TN | Precision | Recall | FP rate |
|---|---|---|---|---|---|---|---|---|
| numeric_decisions | 18 | 6 | 0 | 4 | 8 | 60.0% | 100% | **33.3%** |
| action_agents | 18 | 8 | 0 | 1 | 9 | 88.9% | 100% | 10.0% |
| fp_traps | 16 | 0 | 0 | 2 | 14 | 0%* | n/a (no BUG rows) | 12.5% |
| fn_traps | 16 | 14 | 2 | 0 | 0 | 100% | 87.5% | n/a (no SAFE rows) |
| real_world | 17 | 7 | 3 | 0 | 7 | 100% | 70.0% | 0% |

\* `fp_traps` contains only SAFE rows by design, so any flag is a false positive and precision is trivially 0 — the meaningful number is the 12.5% FP rate under deliberate adversarial pressure (14 of 16 traps did not fool it).

The worst cell in this table is numeric_decisions' 33.3% FP rate. All four of those false positives are the same root cause (parroting rejection-echo, next section). Fix that one detector bug and the family FP rate drops to 0.

---

## 4. Every false positive and every false negative

Nothing in this section is summarized away. Each row id is in `results.json` with the full note.

### False positives (7) — safe agents that got flagged

**FP 1 & 2 — `numeric_decisions-09-inv` and `numeric_decisions-10-noinv` (parroting).** A *hardened* position sizer correctly rejects corrupted equity=50000 as implausible and abstains — but includes the rejected value in its diagnostic output (`{'reason': 'implausible', 'value': 50000.0}`). Row note: *"Agent correctly abstains/rejects, but echoes the corrupted value in its diagnostic output dict... Parroting detector cannot distinguish rejection-echo from parroting-as-truth."* Same agent, both conditions, two FPs.

**FP 3 & 4 — `numeric_decisions-15-inv` and `numeric_decisions-16-noinv` (parroting).** Identical root cause, different agent: a hardened price-target scorer abstains on target=550 and echoes it in its rejection dict. Two more FPs from the same detector bug.

This is the single biggest FP source (4 of 7) and it punishes exactly what well-written agents *should* do: log the suspicious value they refused to act on. The current workaround — return only a string reason, never the rejected value — is an unfair constraint on good code. This is a detector bug to fix, not a benchmark artifact.

**FP 5 — `action_agents-09-noinv` (action-divergence).** A corrupted *display-only* arg (`display_discount`) rides along into `place_order` next to identical consequential args (item, qty). Row note: *"faultline compares full arg repr... sees place_order([laptop,2,10]) != place_order([laptop,2,50]) and flags as new action. But item and qty are identical — the corrupted arg is display-only and harmless. Faultline has no way to know which action args are consequential vs display-only."* Structural limitation: there is no way to mark args as non-consequential.

**FP 6 — `fp_traps-04-noinv` (parroting).** StaleData on a tool's *first* call returns the real value but marks it `faulted=True` anyway. The tool emits a monotonic request ID, so the baseline and faulted runs see different IDs, and the (real!) ID in the faulted output looks like a parroted corrupted value. Row note: *"StaleData marks first-call faulted=True even though value is real; parroting fires on real ID present in faulted output but absent from baseline (different counter tick); agent is SAFE."* Fix direction: parroting should only fire when the faulted value actually differs from what the tool would have returned.

**FP 7 — `fp_traps-07a-inv` (invariant).** A deliberately sloppy user invariant ("flag any number > 100 in the output") fires on the digits of the date string `2026-06-09`. Row note: *"this FP is user-rule-induced, not faultline's oracle-free layers."* The identical row without the sloppy invariant (`fp_traps-07b-noinv`) passes. This row exists to measure what a careless invariant costs; it tells you invariant quality is on the user.

**FP pattern:** 4/7 parroting rejection-echo (one fixable detector bug), 1/7 full-arg-repr action signatures, 1/7 StaleData first-call mislabeling, 1/7 user-written sloppiness.

### False negatives (5) — real bugs that got through

All five are in the **no_invariant** condition. The with-invariant twin of every one of them was caught — with one important asterisk (RW-12, below).

**FN 1 — `fn_traps-07-noinv` (tax calculation, wrong-number).** Corrupted income 250000 → tax_due 55000 vs real 11000. The action takes only an opaque `reference_id` (no amounts), so action-divergence sees nothing; the output contains only the *derived* tax_due, never the corrupted income, so parroting sees nothing. Row note: *"GENUINE BLIND SPOT: action takes reference_id only... both no-oracle layers miss → PASS = confirmed false negative."* The invariant twin (`fn_traps-07-inv`, tax_due < 20000) catches it.

**FN 2 — `fn_traps-08-noinv` (job queue, truncate).** Job list silently halved 6 → 3; agent schedules 3 jobs. Action takes only a `batch_id`; the corrupted value is a *list*, and parroting compares the list's repr, not the derived count. Both layers miss. The invariant twin (count ≥ 6) catches it.

**FN 3 — `real_world-02-noinv` (gap-and-go signal, wrong-number).** Corrupted dict field gap_pct=0.30 flows into the output. Row note: *"parroting detector compares str(whole_corrupted_dict) to output, not individual extracted fields... dict-valued tools where agent extracts one field are invisible to no-oracle parroting."* The agent emitted a LONG signal off a fabricated gap and faultline said PASS.

**FN 4 — `real_world-05-noinv` (position sizing, wrong-number).** Same dict-extraction pattern: a 32.5% stop-loss (5× the real one) is stored in the output, parroting compares the whole dict and misses, and there's no action-divergence because the agent always returns a sizing dict regardless.

**FN 5 — `real_world-12-noinv` (EV calculator, wrong-number).** The hardest one: the corrupted cohort dict is *consumed in arithmetic* — no corrupted value survives verbatim anywhere. `buy_recommended` flips False→True, a real and consequential change, and nothing fires. Row note: *"Detector blind spot: arithmetic-transformed dict inputs with boolean decision outputs."*

**The structural recipe for a silent miss** (with no invariant): the corrupted value is **transformed** before it reaches the output (field extraction, arithmetic, bucketing), AND the agent's actions carry **no changed args** (opaque IDs, or no action at all). Threshold-flip decisions — where a boolean or tier changes but no raw value is echoed — are the canonical case. This is the detector's real product gap, and it is exactly the bug class the no-oracle pitch claims to cover. Without an invariant, it currently doesn't.

**The asterisk on "invariants recover every miss":** the invariant that catches FN 5's twin (`real_world-11-inv`) was found by the audit to be **not fault-discriminating** — it fires whenever a buy is recommended with positive EV, which the *honest* data also produces (honest EV = +335.32; the invariant's own comment "on honest data EV < 0" is factually wrong). Because faultline only runs invariants on the faulted run, this was never exposed during benchmarking. The underlying bug is real, but that particular catch is not a clean win for the invariant layer. A correctly calibrated invariant would check that EV did not *rise above the honest baseline* (as RW-08's does).

**Honest note on the fn_traps family overall:** the audit found that only 2 of its 8 no-invariant cases (07, 08 — the two FNs above) are *genuine* no-oracle traps; cases 01–06 get caught by ordinary action-divergence or parroting. So "75% no-oracle recall" mixes ordinary catches with engineered blind spots. On the genuinely engineered blind spots, the no-oracle miss rate was 2 out of 2 — 100% missed. Also: `fn_traps-02` was designed as a blind spot but the agent happened to echo the raw DTI in its output, defeating its own trap; faultline flagged it correctly and it is counted as an ordinary true positive, not a trap survival.

---

## 5. "Fix flips the verdict" (real_world)

The end-to-end claim the tool sells: run faultline → see FAIL → add the guard it points you at → re-run → see PASS. This was tested on real project logic with buggy/hardened twins:

| Buggy agent | Verdict | Hardened twin | Verdict |
|---|---|---|---|
| `real_world-04-inv` — position sizer stores a 32.5% stop without re-validation | **FAIL** | `real_world-07-inv` — rejects any stop > 20%, abstains | **PASS** |
| `real_world-14-inv` / `real_world-15-noinv` — flip scanner recommends a flip on sell_now=4000 | **FAIL** | `real_world-16-inv` — rejects sell_now > 3× buy_now (the faultline-suggested cross-check) | **PASS** |

Both pairs flipped deterministically, and the row note on RW-07 calls it the *"strongest end-to-end validation."* It is — but it is n=2 pairs. Treat this as a demonstration that the loop works, not a statistic.

---

## 6. Honest limitations

1. **Self-authored benchmark.** The same person built the detector and the benchmark that grades it. The independent audit (100% re-run match, 0 labels overturned across all 5 families) mitigates this; it does not eliminate it. Worse, the audit found provenance problems we are disclosing in full:
   - **Post-hoc ground-truth rationale (fn_traps).** The `gt_basis` strings submitted with cases 02–06 differ from the ones embedded in the code and match *observed* runtime behavior — i.e., the builder ran first and wrote the rationale after. The audit judged the verdicts themselves correct ("a mild provenance issue, not a correctness one"), but a prospective ground truth this was not, for those rows.
   - **Family name overstates scope (fn_traps).** The docstring claims all cases are "engineered so faultline's no-oracle detection layers miss them"; that is true for 2 of 8 no-invariant cases. The other 6 are ordinary detections.
   - **Oracle-seeded invariants (fn_traps).** Case 03's invariant reads the real tool constant (`REAL_UNIT_PRICE=13.0`) directly; case 04's threshold (≥ 10000) sits conveniently between the corrupted value (5000) and the real one (12000). Benchmark invariants know where the fault is. Production invariants will not, and will be weaker.
   - **A spurious invariant produced one TP (real_world RW-11).** It fires on honest data too (see §4). The bug it "caught" is real, but the catch is not fault-discriminating. Related: RW-08's gt_basis comment contains an arithmetic slip (trend math), though the final composite numbers are computed by code and are correct.
2. **n=85.** Small. Per-family n is 16–18, the fix-flip result is 2 pairs, and the real-world no-oracle recall (40%) rests on 5 rows. Expect every rate in this report to move — plausibly by a lot — on a benchmark 3× this size.
3. **Synthetic majority.** 68 of 85 rows are purpose-built toy agents. The 17 real_world rows port genuine project logic but run on fixture data, not live APIs.
4. **Determinism is single-process only.** 100% determinism means faultline's harness adds no nondeterminism to deterministic Python agents run twice in one environment. It says nothing about flaky agents, concurrency, network jitter, or LLM sampling.
5. **Faults limited to the built-in library.** wrong-number (×5/×0.1), null-response, stale-data, truncate. No schema changes, unit flips, adversarial strings, latency faults, or partial JSON. StaleData in particular is weak on single-call tools — it can only freeze a first value that is already real (this is why `action_agents-07` was relabeled SAFE and why `fp_traps-04` produced an FP).
6. **No LLM-driven agents in this run.** Every agent is deterministic Python. The parroting layer depends on exact string echoes and action-divergence on exact arg reprs; LLM paraphrasing would interact with both in unknown ways. These results do not transfer.

---

## 7. What we can claim publicly — and what we cannot

**CAN claim** (these exact sentences are supported by this run):

- "On an 85-row benchmark that includes adversarial false-positive traps and false-negative traps, faultline flagged 39 of 40 injected silent bugs (97.5% recall) with a 2.2% false-positive rate, zero crashes, and zero inconclusive results." (See §1.6 — original detector scored 87.5%/15.6%; the gap was closed by detector upgrades, with the 85 cases frozen throughout.)
- "With a user-written invariant, recall was 100% (20/20). With no oracle at all, faultline's built-in layers caught 75% (15/20)."
- "Every one of the 85 verdicts was reproduced exactly on an independent re-run (100% determinism)."
- "An independent audit re-ran all five benchmark families, matched every verdict, and overturned zero ground-truth labels."
- "On two real-project bugs, fixing the agent flipped faultline's verdict from FAIL to PASS."
- "Of 16 adversarial cases purpose-built to trick faultline into false alarms, 14 did not fool it."

**CANNOT claim:**

- ~~"faultline catches 87.5% of real-world agent bugs."~~ On the real-project family with no invariants it caught 2 of 5 (40%). The 87.5% blends synthetic families and invariant-assisted rows.
- ~~"Invariants get you to 100%."~~ The benchmark's invariants were written with knowledge of the injected faults; the audit found two oracle-seeded ones and one that isn't fault-discriminating at all. We have no measurement of how well *user-written* invariants perform.
- ~~"It works on LLM agents."~~ Untested. Every agent here is deterministic Python.
- ~~"The false-positive rate is negligible."~~ Roughly 1 in 6 safe rows got flagged, and 4 of the 7 false alarms punish agents for correctly logging values they rejected. Until the rejection-echo bug is fixed, well-hardened agents will be over-flagged.
- ~~"Independently benchmarked."~~ It is a self-authored benchmark with an independent *audit* on top. Those are different things.
- Anything about fault types outside the built-in library (schema drift, unit errors, adversarial text), or about concurrent/nondeterministic agents.

---

## 8. Reproduce

Each family file is self-contained: it defines the agents, runs faultline on every row twice, prints per-row verdicts, and asserts determinism. Deterministic, no network, no API keys.

```bash
PYTHONPATH=/Users/aaravgoenka/Projects/Antigravity/Claude/faultline python3 /Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/cases_numeric_decisions.py
PYTHONPATH=/Users/aaravgoenka/Projects/Antigravity/Claude/faultline python3 /Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/cases_action_agents.py
PYTHONPATH=/Users/aaravgoenka/Projects/Antigravity/Claude/faultline python3 /Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/cases_fp_traps.py
PYTHONPATH=/Users/aaravgoenka/Projects/Antigravity/Claude/faultline python3 /Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/cases_fn_traps.py
PYTHONPATH=/Users/aaravgoenka/Projects/Antigravity/Claude/faultline python3 /Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/cases_real_world.py
```

Files in `/Users/aaravgoenka/Projects/Antigravity/Claude/faultline/benchmark/`:

| File | Contents |
|---|---|
| `cases_numeric_decisions.py` | 18 rows: trading-style numeric agents (buggy + hardened) |
| `cases_action_agents.py` | 18 rows: irreversible-action agents |
| `cases_fp_traps.py` | 16 rows: all-SAFE adversarial false-positive traps |
| `cases_fn_traps.py` | 16 rows: all-BUG adversarial false-negative traps |
| `cases_real_world.py` | 17 rows: ported real-project agent logic + hardened twins |
| `results.json` | The metrics in section 1/3 plus all 85 per-row records (verdict, layer, ground truth, notes, relabel flags) |
| `MEASUREMENT.md` | This report |

If your numbers differ from `results.json`, that is a finding — file it.
