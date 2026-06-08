# PR to pandas-ai (sinaptik-ai) — "Reject NaN/inf numeric results instead of returning them as valid"

**Repo:** https://github.com/sinaptik-ai/pandas-ai  (23.5k★, active — May 2026)
**Fork branch (pushed):** https://github.com/sinaptik-ai/pandas-ai/compare/main...aaravanmay:pandas-ai:reject-nan-number
**Status:** FILED — PR #1894 (open).

## What it fixes
`ResponseParser._validate_response` (`pandasai/core/response/parser.py`) validates a
`number` result with `isinstance(result["value"], (int, float, np.int64))`. But **`NaN`
and `inf` are floats**, so they pass this check, get wrapped in a `NumberResponse`, and are
returned as the answer — with no error.

This is exactly the silent-wrong case: when the generated code aggregates over an **empty
result** — e.g. `df["sales"].mean()` after a `WHERE` clause that matched zero rows — pandas
returns `nan`. The user (or downstream charting code) then receives `nan` as a confident
numeric answer with no indication anything went wrong.

## The fix — `pandasai/core/response/parser.py`
After the existing numeric `isinstance` check, add a finite check:

```python
            if isinstance(result["value"], float) and not np.isfinite(result["value"]):
                raise InvalidOutputValueMismatch(
                    "Invalid output: Numeric result is NaN or infinite (likely an aggregation over empty data)."
                )
```

`np` is already imported. `np.isfinite` covers both NaN and inf; `np.float64` subclasses
`float` so it's covered too. Booleans/ints are unaffected.

## The test — `tests/test_nan_number_rejected.py` (in the fork)
Asserts NaN and inf both raise `InvalidOutputValueMismatch`, and a normal number (42) still
parses. No LLM call.

**Verified:** with the fix → **3 passed**; on `main` → the NaN and inf tests **FAIL**
(`DID NOT RAISE` — they return `NumberResponse(nan)`).

## Friendly PR title + body
**Title:** Reject NaN/inf numeric results instead of returning them as a valid answer

**Body:**
> `_validate_response` accepts a `number` result via `isinstance(value, (int, float,
> np.int64))`, but `NaN` and `inf` are floats and pass that check — so they're returned as
> a valid `NumberResponse`. This happens whenever generated code aggregates over an empty
> result (e.g. `df["sales"].mean()` when a filter matched no rows): the user gets `nan` as a
> confident answer, with no error.
>
> This adds a finite-number check that raises `InvalidOutputValueMismatch` for NaN/inf.
> Includes a regression test (no LLM) that fails on `main` and passes with the change.

## To file (≈30 sec)
1. Open the compare URL above → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check `_validate_response` still matches current `main` first.)
