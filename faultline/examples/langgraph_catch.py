"""faultline catching a real LangGraph create_react_agent silently doing the wrong thing.

This builds a REAL `create_react_agent` graph (real ToolNode, real tool
execution) whose agent restocks a SKU to 250 by reading inventory then ordering
the shortfall. faultline corrupts the `get_inventory` tool and catches the agent
placing a wrong order — with no error anywhere.

The "model" here is a small DETERMINISTIC stand-in (a real langchain ChatModel
subclass) so the catch is reproducible and needs no API key. Its decisions
genuinely depend on the (corrupted) tool result — so the silent failure is real,
just deterministic. The live-LLM equivalent is examples/llm_agent_proof.py.

    pip install faultline langgraph langchain-core
    python -m faultline.examples.langgraph_catch
"""
from __future__ import annotations

import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import tool as lc_tool
from langgraph.prebuilt import create_react_agent

import faultline as fl

TARGET = 250


@lc_tool
def get_inventory(sku: str) -> dict:
    """Current on-hand units for a SKU."""
    return {"sku": sku, "units": 240}      # true count: 240 -> correct order is 10


@lc_tool
def place_order(sku: str, qty: int) -> dict:
    """Place a restock order for `qty` units of `sku`."""
    return {"status": "submitted", "sku": sku, "qty": qty}


def _units_from(text):
    m = re.search(r"units['\"]?\s*[:=]\s*(-?\d+)", str(text))
    return int(m.group(1)) if m else None


class RestockModel(BaseChatModel):
    """A deterministic stand-in for an LLM agent: read inventory, then order the
    shortfall to reach TARGET. Its order quantity is computed from the tool
    result it actually receives — so a corrupted reading produces a wrong order."""

    @property
    def _llm_type(self):
        return "restock-deterministic"

    def bind_tools(self, tools, **kwargs):
        return self  # accept the tools langgraph binds; we script the calls

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        def last_tool(name):
            for msg in reversed(messages):
                if isinstance(msg, ToolMessage) and getattr(msg, "name", None) == name:
                    return msg
            return None

        inv = last_tool("get_inventory")
        ordered = last_tool("place_order")
        if ordered is not None:
            ai = AIMessage(content="Done: %s" % ordered.content)
        elif inv is not None:
            units = _units_from(inv.content)
            if units is None:
                ai = AIMessage(content="No inventory reading — not ordering.")
            else:
                qty = max(0, TARGET - units)
                if qty > 0:
                    ai = AIMessage(content="", tool_calls=[{
                        "name": "place_order",
                        "args": {"sku": "A-12", "qty": qty},
                        "id": "call_po", "type": "tool_call"}])
                else:
                    ai = AIMessage(content="Already at/above target — not ordering.")
        else:
            ai = AIMessage(content="", tool_calls=[{
                "name": "get_inventory",
                "args": {"sku": "A-12"},
                "id": "call_gi", "type": "tool_call"}])
        return ChatResult(generations=[ChatGeneration(message=ai)])


def build_instrumented_agent():
    """A real create_react_agent graph with faultline wrapped around its tools."""
    graph = create_react_agent(RestockModel(), [get_inventory, place_order])
    fl.instrument_langgraph(graph, actions=["place_order"])   # place_order won't really fire under test

    def agent(task):
        out = graph.invoke({"messages": [HumanMessage(content="restock A-12 to 250")]})
        return out["messages"][-1].content

    return agent


def run():
    agent = build_instrumented_agent()
    # WrongNumber factor 0.2: an UNDER-reading inventory (240 -> 48) makes the agent
    # over-order. The corrupted reading drives a wrong, confident action that the
    # zero-oracle detector catches via action-divergence (place_order fires with a
    # quantity it never would on real data).
    #
    # Honest scope note: this is asymmetric. An OVER-reading corruption (factor 2.0+)
    # makes the agent order *nothing* — no action diverges, so the no-oracle layer
    # does NOT catch it. That case needs an invariant (e.g. "order must restore
    # stock to target"). Zero-oracle catches the harmful-action direction; the
    # silently-correct-looking direction is an invariant's job. We don't claim the
    # built-in detector catches every inventory corruption.
    result = fl.check(
        agent, {},
        faults=[fl.WrongNumber(factor=0.2, targets=["get_inventory"])],
        invariants=[],
        trials=3,
    )
    result.report()
    return result


if __name__ == "__main__":
    import sys
    res = run()
    bad = [r for r in res.rows if r["verdict"] in ("FAIL", "CRASH")]
    sys.exit(1 if bad else 0)
