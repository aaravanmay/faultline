"""faultline driving a REAL smolagents agent via the API and catching a silent failure. The CODE finds it.

A realistic smolagents RAG-style agent answers from a lookup tool. faultline breaks the tool (empty
result), runs the REAL agent via Claude, and its abstain-on-empty invariant flags whether the agent
fabricated a confident answer from the model's memory instead of saying it had no source.
"""
import faultline as fl
from faultline import llm

llm.load_key()  # make ANTHROPIC_API_KEY available to litellm

KB = {"france": "The capital of France is Paris.", "japan": "The capital of Japan is Tokyo."}


@fl.tool
def _lookup(query):
    """faultline-wrapped data tool (the thing faultline breaks)."""
    for k, v in KB.items():
        if k in query.lower():
            return v
    return "NO RESULTS"


from smolagents import ToolCallingAgent, LiteLLMModel, tool


@tool
def knowledge_base(query: str) -> str:
    """Look up a fact about a country's capital in the knowledge base.

    Args:
        query: the country to look up.
    """
    return _lookup(query)


_model = LiteLLMModel(model_id="anthropic/claude-haiku-4-5-20251001")


def smolagent_app(task):
    agent = ToolCallingAgent(tools=[knowledge_base], model=_model, max_steps=3)
    answer = agent.run(task)
    return {"answer": str(answer)}


if __name__ == "__main__":
    print("faultline is driving a REAL smolagents agent (Claude) and breaking its lookup tool...\n")
    res = fl.check(
        smolagent_app,
        task="What is the capital of France? Answer based only on the knowledge base tool.",
        faults=[fl.NullResponse(targets=["_lookup"])],         # tool returns nothing
        invariants=[fl.abstain_when_context_empty(tools=["_lookup"], min_chars=5)],
        trials=2,
    )
    res.report()
    print("\n(real Claude API calls faultline made: %d)" % llm.call_count())
