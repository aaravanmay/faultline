"""faultline suite for pandas-ai — catches the NaN-as-valid-answer class from PR #1894.

What it tests: a data agent fetches rows from a tool, aggregates with pandas, and
hands the result to pandas-ai's REAL ResponseParser (pandasai.core.response.parser
— the exact code path PR #1894 hardens). faultline corrupts the upstream data the
way real systems do (truncated page, empty payload, bent numbers) and fails CI if
the agent returns a non-finite "valid number" with no error raised.

Verified against installed pandasai: ResponseParser.parse({"type": "number",
"value": nan}) returns NumberResponse(nan) silently — this suite catches that.

Run:  pip install faultline pandasai pandas  &&  faultline run faultline_suite.py
"""
import math

import pandas as pd

import faultline as fl
from pandasai.core.response.parser import ResponseParser

SALES = {"west": [120.0, 95.0, 143.0, 88.0], "east": [101.0, 99.0, 87.0]}


@fl.tool
def get_sales_rows(region):
    """Where the data comes from in a real system (warehouse/API page)."""
    return list(SALES.get(region, []))


def average_sales_agent(task):
    rows = get_sales_rows(task["region"])
    mean = pd.Series(rows, dtype="float64").mean()          # empty rows -> NaN
    result = {"type": "number", "value": float(mean)}
    parsed = ResponseParser().parse(result)                  # the PR #1894 code path
    return {"answer": parsed.value}


def numeric_answer_finite(run):
    out = run.get("output") or {}
    v = out.get("answer")
    if isinstance(v, float) and not math.isfinite(v):
        return ("agent returned %r as a valid numeric answer — an aggregation over "
                "empty/corrupted data slipped through with no error" % v)


def faultline_suite():
    return {
        "agent": average_sales_agent,
        "task": {"region": "west"},
        "faults": [
            fl.Truncate(targets=["get_sales_rows"]),      # partial/empty page -> mean = NaN
            fl.NullResponse(targets=["get_sales_rows"]),  # empty payload
            fl.WrongNumber(targets=["get_sales_rows"]),   # bent values (sanity band)
        ],
        "invariants": [numeric_answer_finite],
        "trials": 3,
    }
