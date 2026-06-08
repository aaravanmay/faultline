"""faultline GENUINELY catching the real pandas-ai NaN bug (no LLM, no fork — the REAL library).

Run:  python3 bench/tool_caught/pandas_ai_nan.py

A pandas-ai-style analyst queries data through a tool, aggregates it, and validates the result
with pandas-ai's REAL ResponseParser. faultline injects a realistic fault (the query matched zero
rows) and its own deterministic invariant `numeric_answer_finite` flags the silent NaN answer that
the real pandas-ai validator waved through. This is the tool catching the bug, not code review.
"""
import pandas as pd

import faultline as fl
from pandasai.core.response.parser import ResponseParser  # the REAL released pandas-ai (unpatched)

SALES = pd.DataFrame({"region": ["US", "US", "EU"], "amount": [100, 200, 300]})


@fl.tool
def run_sql_query(region):
    """The data tool the agent depends on. faultline is allowed to break this."""
    return SALES[SALES.region == region]


def analyst_agent(task):
    """Query -> aggregate -> validate with pandas-ai's real parser (the function with the bug)."""
    df = run_sql_query(task["region"])
    raw = {"type": "number", "value": df["amount"].mean()}      # generated-code-style aggregation
    response = ResponseParser().parse(raw)                       # REAL pandas-ai validation
    return {"answer": response.value}


class EmptyResult(fl.Fault):
    """Realistic fault: the query matched ZERO rows (a WHERE filter, a stale/empty index,
    a rate-limited source). Returns an empty result set, exactly like a real zero-hit query."""
    name = "empty-result"

    def hit(self, tool_name, args, kwargs, result):
        return result.iloc[0:0] if hasattr(result, "iloc") else result


if __name__ == "__main__":
    res = fl.check(
        analyst_agent,
        task={"region": "US"},
        faults=[EmptyResult(targets=["run_sql_query"])],
        invariants=[fl.numeric_answer_finite()],
        trials=3,
    )
    res.report()
