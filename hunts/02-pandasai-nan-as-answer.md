# Hunt 02 — pandas-ai returned NaN as a valid number

**Target:** [pandas-ai](https://github.com/sinaptik-ai/pandas-ai) (24k★, "chat with your data" agent)
**Label:** CATCH — [PR #1894](https://github.com/sinaptik-ai/pandas-ai/pull/1894) (open)

## The setup
A data agent fetches rows from a tool and computes an aggregate with pandas, then hands the
result to pandas-ai's real `ResponseParser` (the code path that decides "is this a valid
answer?"). I wrapped the data source and gave faultline one rule: *a numeric answer must be
finite.*

## What happened
When the upstream rows came back empty or truncated — a `WHERE` clause that matched nothing, a
partial page — the aggregate became `NaN`. And `NaN` is a `float`, so it sails straight through
pandas-ai's `isinstance(value, (int, float))` check and is returned to the user as a valid
number. **The agent confidently answers "the average is NaN" with no error.**

```
import faultline as fl                       # verified on installed pandasai
...
⚠  null-response  FAIL   [SILENT, SILENT, SILENT]
   agent returned nan as a valid numeric answer — an aggregation over empty data slipped through
⚠  wrong-number   FAIL   [SILENT, SILENT, SILENT]
   a number in its answer scaled in lockstep with the injected corruption (111.5 -> 557.5)
Resilience: 1/3 faults handled
```

The second line is a bonus catch: faultline's built-in detector noticed the answer scaled by
the exact factor of the injected corruption — a *derived-value* silent failure, where the bad
number is transformed (×5 here) so it never appears verbatim. No hand-written rule for that one.

## The fix
Reject non-finite numeric results (`NaN`/`inf`) in the response parser instead of returning them
as valid — they almost always mean "aggregation over empty data." Test fails before, passes after.

## Why it matters
A "chat with your data" tool that answers `NaN` as if it were a real number is exactly the
"200 OK, wrong answer" failure — a confident wrong number with a decision riding on it.
