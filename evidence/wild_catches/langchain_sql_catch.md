```

faultline · check report
==============================================================
baseline: agent ran OK (no fault)
--------------------------------------------------------------
⚠  wrong-number          FAIL           [SILENT, SILENT]  invariant violated: reported [284731] as the total, not the true 2847312, with no caveat
⚠  truncate              FAIL           [SILENT, SILENT]  invariant violated: reported [932312] as the total, not the true 2847312, with no caveat
--------------------------------------------------------------
Resilience: 0/2 faults handled
⚠ 2 SILENT failure(s) — the dangerous kind:
    wrong-number: invariant violated: reported [284731] as the total, not the true 2847312, with no caveat
    truncate: invariant violated: reported [932312] as the total, not the true 2847312, with no caveat

Suggested fixes (then re-run to verify):
  - wrong-number: guard the value before any irreversible action — cross-check a 2nd independent source or range/sanity-check it, and assert an invariant (refuse to act if the value is implausible).
  - truncate: verify completeness before counting/aggregating — check pagination or a total-count and fail loudly if you only received a partial page.

```
