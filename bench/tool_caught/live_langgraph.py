"""faultline driving a REAL LangGraph ReAct agent via the API and catching a silent failure. CODE finds it.

A LangGraph create_react_agent answers a balance question using a tool. faultline corrupts the tool's
number (WrongNumber), runs the REAL agent via Claude, and its poison-parroting detector flags that the
agent reported the corrupted value as fact with no validation - a silent wrong answer.
"""
import faultline as fl
from faultline import llm
llm.load_key()

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool as lc_tool
from langgraph.prebuilt import create_react_agent

BALANCE = {"alice": 100}


@fl.tool
def _get_balance(account):
    return BALANCE[account]


@lc_tool
def get_balance(account: str) -> int:
    """Return the current account balance, in dollars, for the given account name."""
    return _get_balance(account)


_model = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
_graph = create_react_agent(_model, [get_balance])


def bank_agent(task):
    out = _graph.invoke({"messages": [("user", task)]})
    return {"answer": out["messages"][-1].content}


if __name__ == "__main__":
    print("faultline is driving a REAL LangGraph agent (Claude) and corrupting its balance tool...\n")
    res = fl.check(
        bank_agent,
        task="What is alice's account balance in dollars? Give the number.",
        faults=[fl.WrongNumber(factor=5, targets=["_get_balance"])],   # 100 -> 500
        invariants=[fl.no_poison_parroting(targets=["_get_balance"])],
        trials=2,
    )
    res.report()
