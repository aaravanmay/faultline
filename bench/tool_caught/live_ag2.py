"""faultline driving a REAL ag2 (AutoGen) multi-agent setup via the API. The CODE finds the failure."""
import os
import faultline as fl
from faultline import llm
llm.load_key()
from autogen import ConversableAgent, register_function

BALANCE = {"alice": 100}

@fl.tool
def _get_balance(account):
    return BALANCE[account]

def get_balance(account: str) -> int:
    """Return the account balance in dollars for the given account name."""
    return _get_balance(account)

_cfg = {"config_list": [{"model": "claude-haiku-4-5-20251001",
                         "api_key": os.environ.get("ANTHROPIC_API_KEY", ""), "api_type": "anthropic"}],
        "cache_seed": None}


def bank_agent(task):
    assistant = ConversableAgent(name="assistant",
        system_message="You are a banking assistant. Call get_balance, then state the balance and end with TERMINATE.",
        llm_config=_cfg)
    user = ConversableAgent(name="user", human_input_mode="NEVER", llm_config=False,
        is_termination_msg=lambda m: "TERMINATE" in (m.get("content") or ""))
    register_function(get_balance, caller=assistant, executor=user,
                      name="get_balance", description="Get the account balance in dollars for an account name.")
    res = user.initiate_chat(assistant, message=task, max_turns=4, silent=True)
    answer = ""
    for m in reversed(res.chat_history):
        if m.get("content"):
            answer = m["content"]; break
    return {"answer": answer}


if __name__ == "__main__":
    print("faultline driving a REAL ag2 multi-agent setup (Claude), corrupting its balance tool...\n")
    res = fl.check(bank_agent, "What is alice's balance in dollars? Give just the number.",
        faults=[fl.WrongNumber(factor=5, targets=["_get_balance"])],
        invariants=[fl.no_poison_parroting(targets=["_get_balance"])], trials=2)
    res.report()
