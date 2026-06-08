"""faultline driving a REAL LangChain AgentExecutor via the API. The CODE finds the silent failure."""
import faultline as fl
from faultline import llm
llm.load_key()
from langchain_anthropic import ChatAnthropic
from langchain_core.tools import tool as lc_tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.agents import create_tool_calling_agent, AgentExecutor

REVENUE = {"q3": 100}

@fl.tool
def _get_revenue(quarter):
    return REVENUE[quarter]

@lc_tool
def get_revenue(quarter: str) -> int:
    """Return revenue in millions of dollars for the given quarter (e.g. 'q3')."""
    return _get_revenue(quarter)

_model = ChatAnthropic(model="claude-haiku-4-5-20251001", temperature=0)
_prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a financial assistant. Use the get_revenue tool to answer."),
    ("human", "{input}"),
    MessagesPlaceholder("agent_scratchpad"),
])
_agent = create_tool_calling_agent(_model, [get_revenue], _prompt)
_executor = AgentExecutor(agent=_agent, tools=[get_revenue], verbose=False)

def fin_agent(task):
    out = _executor.invoke({"input": task})
    return {"answer": out["output"]}

if __name__ == "__main__":
    print("faultline driving a REAL LangChain AgentExecutor (Claude), corrupting its revenue tool...\n")
    res = fl.check(fin_agent, "What was Q3 revenue in millions? Give just the number.",
        faults=[fl.WrongNumber(factor=9, targets=["_get_revenue"])],   # 100 -> 900
        invariants=[fl.no_poison_parroting(targets=["_get_revenue"])], trials=2)
    res.report()
