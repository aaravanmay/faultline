# PR to DB-GPT (eosphoros-ai) — "Fix wrong column index for chart label on NULL rows"

**Repo:** https://github.com/eosphoros-ai/DB-GPT  (18.9k★, active — pushed Jun 2026)
**Fork branch (pushed):** https://github.com/eosphoros-ai/DB-GPT/compare/main...aaravanmay:DB-GPT:fix-null-row-chart-label
**Status:** STAGED — fork pushed, verified. NOT filed yet (Aarav to review + click "Create PR").

## What it fixes
`DashboardDataLoader.get_chart_values_by_data`
(`packages/dbgpt-app/src/dbgpt_app/scene/chat_dashboard/data_loader.py`) builds chart
series from a SQL result. It computes `primary_index` (the dimension column:
string → datetime → id) and the **non-NULL** row branch correctly labels each point with
`data[primary_index]`. But the **NULL-handling** branch hard-codes `data[string_index]`.

`string_index` is `-1` whenever the result has **no string column** — e.g. a
`(event_date, sales, cost)` query keyed on a datetime. So `data[string_index]` is
`data[-1]` = the **last column's value** (here `cost`), not the dimension. With
`ValueItem.name` typed as `str`, that raises a `ValidationError` on a numeric last column
(current pydantic), and mislabels the chart series under lenient configs. Either way the
label is wrong, and it triggers on the common case: a datetime/id-keyed chart query where
any row has a NULL.

This is a one-line indexing fix: make the NULL branch use the same `primary_index` the
non-NULL branch already uses.

## The fix — `data_loader.py`, NULL-handling branch
```python
# before:
                            name=data[string_index],
# after:
                            name=str(data[primary_index]),
```
(plus a comment explaining why). No behavior change for non-NULL rows or string-keyed
results.

## The test — `tests/test_chart_label_null_row.py` (in the fork)
Calls `get_chart_values_by_data` with a datetime-keyed result containing a NULL row;
asserts no label equals the last column's value and that the date is used. No DB, no LLM.

**Verified:** with the fix → **PASS** (labels are the dates); on `main` → **FAIL**
(raises `ValidationError` / uses `150`, the cost column). Verified by loading the real
`data_loader.py` source and running the function directly.

## Friendly PR title + body
**Title:** Fix wrong column index for chart series label on rows containing NULL

**Body:**
> `get_chart_values_by_data` computes `primary_index` (string → datetime → id) and the
> non-NULL branch labels points with `data[primary_index]`. The NULL-handling branch,
> though, uses `data[string_index]`. When the result has no string column (a datetime/id
> primary dimension), `string_index == -1`, so the NULL row is labeled with the **last
> column's value** instead of the dimension — which raises a `ValidationError`
> (`ValueItem.name` is `str`) on a numeric last column, or mislabels the series.
>
> This makes the NULL branch use the same `primary_index` as the non-NULL branch.
> Includes a regression test (no DB / no LLM) that fails on `main` and passes with the fix.

## To file (≈30 sec)
1. Open the compare URL above → **"Create pull request"**.
2. Paste the title + body. Submit.
3. (Re-check the branch still matches current `main` first.)
