"""faultline driving a REAL agno agent via the API. The CODE finds the silent failure."""
import faultline as fl
from faultline import llm
llm.load_key()
from agno.agent import Agent
from agno.models.anthropic import Claude

BALANCE = {"alice": 100}

@fl.tool
def _get_balance(account):
    return BALANCE[account]

def get_balance(account: str) -> str:
    """Return the account balance in dollars for the given account name."""
    return str(_get_balance(account))

_agent = Agent(model=Claude(id="claude-haiku-4-5-20251001"), tools=[get_balance], markdown=False, telemetry=False)

def bank_agent(task):
    r = _agent.run(task)
    return {"answer": str(getattr(r, "content", r))}

if __name__ == "__main__":
    print("faultline driving a REAL agno agent (Claude), corrupting its balance tool...\n")
    res = fl.check(bank_agent, "What is alice's balance in dollars? Give just the number.",
        faults=[fl.WrongNumber(factor=5, targets=["_get_balance"])],
        invariants=[fl.no_poison_parroting(targets=["_get_balance"])], trials=2)
    res.report()
