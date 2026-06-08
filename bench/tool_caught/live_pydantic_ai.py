"""faultline driving a REAL pydantic-ai agent via the API. The CODE finds the silent failure."""
import faultline as fl
from faultline import llm
llm.load_key()
from pydantic_ai import Agent

BALANCE = {"alice": 100}

@fl.tool
def _get_balance(account):
    return BALANCE[account]

agent = Agent("anthropic:claude-haiku-4-5-20251001",
              system_prompt="You are a banking assistant. Use the get_balance tool to answer.")

@agent.tool_plain
def get_balance(account: str) -> int:
    """Return the account balance in dollars for the given account name."""
    return _get_balance(account)

def bank_agent(task):
    r = agent.run_sync(task)
    return {"answer": str(getattr(r, "output", getattr(r, "data", r)))}

if __name__ == "__main__":
    print("faultline driving a REAL pydantic-ai agent (Claude), corrupting its balance tool...\n")
    res = fl.check(bank_agent, "What is alice's balance in dollars? Give just the number.",
        faults=[fl.WrongNumber(factor=5, targets=["_get_balance"])],
        invariants=[fl.no_poison_parroting(targets=["_get_balance"])], trials=2)
    res.report()
