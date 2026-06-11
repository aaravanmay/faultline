**What this changes**
One-line summary.

**Why**
The failure it catches / the friction it removes.

**Checklist**
- [ ] `python3 tests/run_all.py` prints `ALL GREEN ✓`
- [ ] Added a test that fails before this change and passes after
- [ ] 3.9-clean (no `X | Y` unions, no `match`, `from __future__ import annotations` if needed)
- [ ] If I touched `faultline/detect.py`: re-ran the 85-case benchmark, **zero regression** (40 FAIL / 45 PASS)
- [ ] Docs honest — no new overclaim; benchmark numbers not attached to LLM/framework claims (see `CAPABILITIES.md`)
