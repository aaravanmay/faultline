"""faultline driving a REAL LlamaIndex-LLM RAG agent via the API. The CODE finds the silent failure.

A realistic (naive) RAG agent retrieves context then answers via LlamaIndex's Anthropic LLM. faultline
empties the retrieval; its abstain-on-empty detector flags whether the agent fabricated a confident
answer from the model's memory instead of saying it had no source.
"""
import faultline as fl
from faultline import llm
llm.load_key()
from llama_index.llms.anthropic import Anthropic

_model = Anthropic(model="claude-haiku-4-5-20251001", temperature=0.0)

KB = {"france": "The capital of France is Paris."}

@fl.tool
def retrieve(query):
    return [v for k, v in KB.items() if k in query.lower()]

def rag_agent(task):
    context = "\n".join(retrieve(task) or [])
    # a typical quick RAG prompt (no explicit 'abstain if empty' instruction) -> realistic
    resp = _model.complete("Use the context to answer the question.\nContext:\n%s\nQuestion: %s\nAnswer:" % (context, task))
    return {"answer": str(resp)}

if __name__ == "__main__":
    print("faultline driving a REAL LlamaIndex-LLM RAG agent (Claude), emptying its retrieval...\n")
    res = fl.check(rag_agent, "What is the capital of France?",
        faults=[fl.NullResponse(targets=["retrieve"])],
        invariants=[fl.abstain_when_context_empty(tools=["retrieve"], min_chars=5)], trials=2)
    res.report()
