"""faultline driving a REAL CrewAI agent via the API. The CODE finds the silent failure."""
import faultline as fl
from faultline import llm
llm.load_key()
from crewai import Agent, Task, Crew
from crewai.tools import tool as crew_tool

BALANCE = {"alice": 100}

@fl.tool
def _get_balance(account):
    return BALANCE[account]

@crew_tool("get_balance")
def get_balance(account: str) -> str:
    """Return the account balance in dollars for the given account name."""
    return str(_get_balance(account))

def bank_agent(_task):
    agent = Agent(role="Banker", goal="Report the customer's exact account balance",
                  backstory="You answer balance questions using the get_balance tool.",
                  tools=[get_balance], llm="anthropic/claude-haiku-4-5-20251001", verbose=False)
    task = Task(description="What is alice's account balance in dollars? Give just the number.",
                expected_output="the balance number", agent=agent)
    crew = Crew(agents=[agent], tasks=[task], verbose=False)
    return {"answer": str(crew.kickoff())}

if __name__ == "__main__":
    print("faultline driving a REAL CrewAI agent (Claude), corrupting its balance tool...\n")
    res = fl.check(bank_agent, "go",
        faults=[fl.WrongNumber(factor=5, targets=["_get_balance"])],
        invariants=[fl.no_poison_parroting(targets=["_get_balance"])], trials=2)
    res.report()
