"""LIVE test on a REAL LangChain agent (the most popular agent framework).

This is the launch-grade proof: not my hand-rolled loop, but a standard
LangChain tool-calling agent (create_tool_calling_agent + AgentExecutor) powered
by Claude Haiku. Its tools are faultline-wrapped, so faultline can break them and
watch whether a real LangChain agent fails silently.

Run:  ANTHROPIC_API_KEY=... python3 -m faultline.examples.langchain_agent
"""
from __future__ import annotations

import re

from faultline.trace import tool as fl_tool, wrap as fl_wrap
from faultline.runner import check
from faultline.faults import WrongNumber, NullResponse, Timeout

from langchain_anthropic import ChatAnthropic
from langchain_core.tools import StructuredTool
from langchain_core.prompts import ChatPromptTemplate
from langchain.agents import create_tool_calling_agent, AgentExecutor

MODEL = "claude-haiku-4-5-20251001"
INVENTORY = {"widget": 2}
PRICES = {"widget": 9.99}
REAL_ORDERS = []


@fl_tool
def get_inventory(item: str) -> int:
    """Units in stock for an item."""
    return INVENTORY[item]


@fl_tool
def get_price(item: str) -> float:
    """Unit price for an item."""
    return PRICES[item]


def _place_order(item: str, qty: int) -> dict:
    REAL_ORDERS.append((item, qty))   # the REAL side effect — must never run under test
    return {"ok": True}
place_order = fl_wrap(_place_order, is_action=True)


_EXEC = None


def _executor():
    global _EXEC
    if _EXEC is not None:
        return _EXEC
    llm = ChatAnthropic(model=MODEL, max_tokens=300, temperature=0)
    tools = [
        StructuredTool.from_function(get_inventory, name="get_inventory", description="Units in stock for an item."),
        StructuredTool.from_function(get_price, name="get_price", description="Unit price for an item."),
        StructuredTool.from_function(place_order, name="place_order", description="Place an order. Only call if there is enough stock."),
    ]
    prompt = ChatPromptTemplate.from_messages([
        ("system", "You are an order-fulfillment agent. Use the tools to check stock and price, then decide. "
                   "Place the order ONLY if there is enough stock for the full quantity. "
                   "End your reply with exactly 'DECISION: BUY' if you placed the order, otherwise 'DECISION: DECLINE'."),
        ("human", "{input}"),
        ("placeholder", "{agent_scratchpad}"),
    ])
    agent = create_tool_calling_agent(llm, tools, prompt)
    _EXEC = AgentExecutor(agent=agent, tools=tools, max_iterations=5, verbose=False, handle_parsing_errors=True)
    return _EXEC


def lc_agent(task):
    """A real LangChain agent. Returns a structured decision so detection is stable."""
    res = _executor().invoke({"input": "A customer wants to buy %d %s(s). Decide whether to fulfill it."
                              % (task["qty"], task["item"])})
    raw = res.get("output", "")
    if isinstance(raw, list):   # Anthropic via LangChain returns a list of content blocks
        text = " ".join(str(b.get("text", "")) if isinstance(b, dict) else str(b) for b in raw)
    else:
        text = str(raw)
    decision = "BUY" if re.search(r"DECISION:\s*BUY", text, re.I) else "DECLINE"
    return {"decision": decision}


def must_not_buy(run):
    out = run.get("output")
    if out and out.get("decision") == "BUY":
        return "agent ORDERED out-of-stock goods (real stock 2 < 3)"
    return None


def main():
    task = {"item": "widget", "qty": 3}   # real stock 2 < 3 → correct = DECLINE
    print("faultline · LIVE test on a real LANGCHAIN agent (Anthropic Haiku)")
    print("  task: buy 3 widgets (only 2 in stock → correct answer is DECLINE)")
    res = check(lc_agent, task, faults=[
        WrongNumber(factor=5, targets=["get_inventory"]),
        NullResponse(targets=["get_inventory"]),
        Timeout(targets=["get_inventory"]),
    ], invariants=[must_not_buy], trials=3)
    res.report()
    print("\nREAL_ORDERS (must be empty):", REAL_ORDERS)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
