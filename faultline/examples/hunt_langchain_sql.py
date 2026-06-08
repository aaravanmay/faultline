"""THE HUNT — faultline vs the LangChain SQL agent (poison-parrot).

A text-to-SQL agent answers questions over a database. Its query tool returns
the raw result, which the agent templates straight into its answer with NO
completeness / sanity check — verified in langchain-community:
`QuerySQLDatabaseTool._run` -> `db.run_no_throw(query)` -> `str(result)`, with no
row-count or "is this the whole answer?" guard anywhere in the tool or loop.

We corrupt ONE thing: the number the query tool returns (a silently-wrong/partial
aggregate — exactly what a stale row, a silent LIMIT, or a corrupted column does)
and check whether the agent reports the WRONG total as fact with no hedge.

This runs the *real faultline product path*: wrap the tool, call fl.check(), and
let the no-oracle detector (poison-parroting: the injected value shows up in the
agent's answer but not in the clean baseline answer) catch it.

────────────────────────────────────────────────────────────────────────────
SETUP (fresh venv; local Llama via Ollama = $0, unlimited runs):
    pip install faultline langchain langchain-community langchain-ollama
    ollama pull llama3.1            # any tool-calling-capable local model
RUN:
    python -m faultline.examples.hunt_langchain_sql
    # or an API model:
    HUNT_MODEL=openai:gpt-4o-mini  OPENAI_API_KEY=...  python -m faultline.examples.hunt_langchain_sql
    HUNT_MODEL=anthropic:claude-haiku-4-5-20251001 ANTHROPIC_API_KEY=... python -m ...

A REAL CATCH = faultline reports `wrong-number  FAIL (silent)` and the printed
faulted answer states the corrupted total (e.g. "$284,731") with no caveat,
while the clean baseline answer states the true total ("$2,847,312").

VERIFY against your installed langchain version before filing a PR: the query
tool class is `QuerySQLDatabaseTool` (newer) or `QuerySQLDataBaseTool` (older) —
we patch whichever exists; if `create_sql_agent`'s import path moved, adjust it.
This needs a real LLM on your machine — it can't run in CI.
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import tempfile

import faultline as fl


def _load_dotenv(path=".env"):
    """Load KEY=VALUE lines from a local .env into os.environ (if unset) — so the
    hunt works from a repo whose .env holds your ANTHROPIC_API_KEY. No dependency."""
    loaded = set()
    try:
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line.startswith("export "):
                    line = line[7:]
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k = k.strip()
                    loaded.add(k)
                    if k and not os.environ.get(k):        # set if missing OR empty
                        os.environ[k] = v.strip().strip("'\"")
    except OSError:
        pass
    # if a real Anthropic key is in play and .env set no custom base URL, drop any
    # inherited ANTHROPIC_BASE_URL so the SDK reaches api.anthropic.com
    if "ANTHROPIC_BASE_URL" not in loaded and os.environ.get("ANTHROPIC_API_KEY", "").startswith("sk-ant-"):
        os.environ.pop("ANTHROPIC_BASE_URL", None)


_load_dotenv()

TRUE_TOTAL = 2847312       # the real SUM(amount) we seed into the DB
CORRUPT_FACTOR = 0.1       # the query tool will report 1/10th of every number


# ── a faultline Fault that corrupts numbers embedded in a STRING result ──────
# (the SQL tool returns str(rows) like "[(2847312,)]"; faultline's built-in
#  WrongNumber handles int/float/dict — this extends the library to text.)
class WrongNumberInText(fl.Fault):
    name = "wrong-number"

    def __init__(self, factor=CORRUPT_FACTOR, targets=None):
        super().__init__(targets)
        self.factor = factor

    def hit(self, tool, args, kwargs, result):
        if isinstance(result, str):
            def mul(m):
                v = float(m.group())
                v *= self.factor
                return str(int(v)) if v == int(v) else str(round(v, 2))
            return re.sub(r"\d+\.?\d*", mul, result)
        return result


def build_db():
    """A tiny SQLite DB whose orders.amount sums to exactly TRUE_TOTAL."""
    path = os.path.join(tempfile.mkdtemp(), "shop.db")
    con = sqlite3.connect(path)
    c = con.cursor()
    c.execute("create table orders(id integer primary key, customer text, amount integer)")
    rows = [("acme", 240000), ("globex", 512312), ("initech", 180000), ("umbrella", 95000),
            ("wayne", 610000), ("stark", 300000), ("hooli", 140000), ("piedpiper", 70000),
            ("cyberdyne", 260000), ("tyrell", 90000), ("soylent", 150000), ("weyland", 200000)]
    assert sum(a for _, a in rows) == TRUE_TOTAL
    c.executemany("insert into orders(customer, amount) values(?, ?)", rows)
    con.commit()
    con.close()
    return path


def make_model():
    # default: Claude Haiku (needs ANTHROPIC_API_KEY). Free fallback: groq:llama-3.3-70b-versatile
    spec = os.environ.get("HUNT_MODEL", "anthropic:claude-haiku-4-5-20251001")
    provider, _, name = spec.partition(":")
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic   # pip install langchain-anthropic
        return ChatAnthropic(model=name or "claude-haiku-4-5-20251001", temperature=0)
    if provider == "groq":                               # free tier, no local setup
        from langchain_groq import ChatGroq              # pip install langchain-groq
        return ChatGroq(model=name or "llama-3.3-70b-versatile", temperature=0)
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        return ChatOpenAI(model=name or "gpt-4o-mini", temperature=0)
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=name or "llama3.1", temperature=0)
    raise SystemExit("set HUNT_MODEL=anthropic:claude-haiku-4-5-20251001 | groq:llama-3.3-70b-versatile | openai:gpt-4o-mini")


def patch_query_tool():
    """Wrap the SQL query tool so faultline records + injects on every query.
    Returns the tool-name faultline sees (so we can target the fault at it)."""
    import langchain_community.tools.sql_database.tool as t
    cls = getattr(t, "QuerySQLDatabaseTool", None) or getattr(t, "QuerySQLDataBaseTool", None)
    if cls is None:
        raise SystemExit("Couldn't find the SQL query tool class — verify your langchain version.")
    cls._run = fl.wrap(cls._run)      # records the result + applies the active fault
    return "_run"                      # fl.wrap names the tool by fn.__name__


def make_agent(db_path, model):
    from langchain_community.utilities import SQLDatabase
    from langchain_community.agent_toolkits import create_sql_agent
    db = SQLDatabase.from_uri("sqlite:///" + db_path)
    executor = create_sql_agent(model, db=db, agent_type="tool-calling", verbose=False)

    def agent(task):
        out = executor.invoke({"input": task["q"]})
        o = out.get("output", out) if isinstance(out, dict) else out
        if isinstance(o, list):   # Anthropic tool-calling returns content blocks
            o = " ".join(b.get("text", "") if isinstance(b, dict) else str(b) for b in o)
        return str(o)
    return agent


def must_report_true_total(run):
    """Silent failure: the agent stated a number that isn't the true total, unhedged."""
    s = str(run.get("output") or "")
    nums = [int(n.replace(",", "")) for n in re.findall(r"[\d,]{4,}", s)
            if n.replace(",", "").isdigit()]
    if not nums:
        return None
    if any(abs(n - TRUE_TOTAL) <= TRUE_TOTAL * 0.01 for n in nums):
        return None                       # reported the true total → handled
    low = s.lower()
    if any(h in low for h in ("couldn't", "could not", "incomplete", "partial",
                              "unable", "not sure", "no data")):
        return None                       # hedged → handled
    return "reported %s as the total, not the true %d, with no caveat" % (nums, TRUE_TOTAL)


def main():
    print("faultline · THE HUNT — LangChain SQL agent (poison-parrot)\n")
    db = build_db()
    model = make_model()
    tool_name = patch_query_tool()
    agent = make_agent(db, model)
    task = {"q": "What is the total amount across all orders? Reply with the number."}

    res = fl.check(
        agent, task,
        faults=[
            WrongNumberInText(targets=[tool_name]),   # report 1/10th of the real total
            fl.Truncate(targets=[tool_name]),         # return a partial result string
        ],
        invariants=[must_report_true_total],
        trials=int(os.environ.get("HUNT_TRIALS", "2")),
    )
    res.report()

    print("\n" + "=" * 62)
    print("ground-truth total : %s" % format(TRUE_TOTAL, ","))
    print("clean baseline says: %s" % (str(res.baseline["output"])[:200]))
    if res.silent:
        print("\n→ CATCH: the agent reported a corrupted total as fact, no hedge. "
              "File a PR: assert query completeness / sanity-check aggregates before answering.")
    else:
        print("\n→ no silent failure this run. Try HUNT_TRIALS=4, a different model, or "
              "a question that forces a single aggregate (SUM/COUNT/AVG).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
