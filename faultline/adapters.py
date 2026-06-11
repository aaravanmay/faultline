"""faultline.adapters — auto-instrument framework agents so their tools are faultline-injectable
WITHOUT manually adding ``@fl.tool`` to each one (the way observability tools auto-instrument).

    import faultline as fl

    fl.instrument_langchain(my_tools)          # wraps each LangChain tool, in place
    # now fl.check / fl.run_once can inject faults into them by their tool name:
    fl.check(agent, task, faults=[fl.WrongNumber(targets=["search"])], invariants=[...])

Each tool's underlying callable is wrapped with faultline's tracer. Outside a faultline run the tools
behave 100% normally (the wrapper is transparent when no run is active). Tool names are the FRAMEWORK's
names, so a fault can target "search", "get_weather", etc. Pass ``actions=[...]`` to mark tools that
take real-world side-effects (their real function won't fire under test — a stub is used instead).
"""
from __future__ import annotations

from .trace import wrap


def _as_tool_list(x):
    """Accept a list of tools, a single tool, or an agent/executor exposing `.tools`."""
    if x is None:
        return []
    if isinstance(x, (list, tuple)):
        return list(x)
    tools = getattr(x, "tools", None)
    if tools is not None:
        try:
            return list(tools)
        except TypeError:
            pass
    return [x]


def _tool_name(t, fallback):
    v = getattr(t, "name", None)
    if isinstance(v, str) and v:
        return v
    meta = getattr(t, "metadata", None)            # LlamaIndex: tool.metadata.name
    if meta is not None:
        v = getattr(meta, "name", None)
        if isinstance(v, str) and v:
            return v
    return fallback


def _wrap_attr(obj, attr, name, is_action):
    """Replace obj.attr with a faultline-wrapped version, if it's a plain callable. Returns True if done."""
    fn = getattr(obj, attr, None)
    if callable(fn) and not getattr(fn, "_faultline_tool", False):
        try:
            setattr(obj, attr, wrap(fn, is_action=is_action, name=name))
            return True
        except Exception:
            return False
    return False


def instrument_langchain(tools_or_agent, actions=None):
    """Auto-wrap a LangChain agent's tools (a list of tools, or an AgentExecutor with ``.tools``).

    Returns what you passed in (mutated in place). ``actions`` = tool names whose real function must
    NOT fire under test (orders, writes, deletes) — faultline stubs them instead.
    """
    actions = set(actions or [])
    wrapped = []
    for i, t in enumerate(_as_tool_list(tools_or_agent)):
        name = _tool_name(t, "tool_%d" % i)
        is_action = name in actions
        # LangChain Tool/StructuredTool → `.func` (sync) and/or `.coroutine`; BaseTool → `._run`
        ok = _wrap_attr(t, "func", name, is_action)
        ok = _wrap_attr(t, "coroutine", name, is_action) or ok
        if not ok:
            ok = _wrap_attr(t, "_run", name, is_action)
        if ok:
            wrapped.append(name)
    return tools_or_agent


def _tools_by_name_of(obj):
    """Return a list of BaseTools from an object exposing tools_by_name / _tools_by_name."""
    tbn = getattr(obj, "tools_by_name", None)
    if tbn is None:
        tbn = getattr(obj, "_tools_by_name", None)
    if isinstance(tbn, dict):
        return list(tbn.values())
    return None


def _extract_langgraph_tools(target):
    """Pull the BaseTool list out of a list of tools, a ToolNode, or a compiled
    create_react_agent / create_agent graph (LangGraph V0 and V1 layouts)."""
    if isinstance(target, (list, tuple)):
        return list(target)
    # a ToolNode (or anything exposing tools_by_name) directly
    direct = _tools_by_name_of(target)
    if direct is not None:
        return direct
    # a compiled graph: find the tool node among .nodes and dig for its tools
    nodes = getattr(target, "nodes", None)
    found = []
    if isinstance(nodes, dict):
        for node in nodes.values():
            for holder in (node, getattr(node, "bound", None),
                           getattr(node, "runnable", None), getattr(node, "node", None)):
                if holder is None:
                    continue
                tools = _tools_by_name_of(holder)
                if tools:
                    found.extend(tools)
    if found:
        # dedupe by id (a tool can appear under multiple node references)
        seen = set()
        uniq = []
        for t in found:
            if id(t) not in seen:
                seen.add(id(t))
                uniq.append(t)
        return uniq
    return [target]


def instrument_langgraph(target, actions=None):
    """Auto-wrap the tools of a LangGraph agent so faultline can inject faults.

    Accepts a list of tools, a ToolNode, or a compiled ``create_react_agent`` /
    ``create_agent`` graph — and wraps each tool's underlying callable IN PLACE.
    Outside a faultline run the tools behave normally. Returns the list of
    wrapped tool names (so you know what faults can target).

        from langgraph.prebuilt import create_react_agent
        graph = create_react_agent(model, tools)
        names = fl.instrument_langgraph(graph, actions=["place_order"])
        # now: fl.check(lambda t: graph.invoke(t), task,
        #               faults=[fl.WrongNumber(targets=["get_inventory"])])
    """
    actions = set(actions or [])
    wrapped = []
    for i, t in enumerate(_extract_langgraph_tools(target)):
        name = _tool_name(t, "tool_%d" % i)
        is_action = name in actions
        ok = _wrap_attr(t, "func", name, is_action)
        ok = _wrap_attr(t, "coroutine", name, is_action) or ok
        if not ok:
            ok = _wrap_attr(t, "_run", name, is_action)
        if ok:
            wrapped.append(name)
    return wrapped


def instrument_llamaindex(tools_or_agent, actions=None):
    """Auto-wrap LlamaIndex FunctionTools (a list, or an agent/engine exposing ``.tools``)."""
    actions = set(actions or [])
    wrapped = []
    for i, t in enumerate(_as_tool_list(tools_or_agent)):
        name = _tool_name(t, "tool_%d" % i)
        is_action = name in actions
        # LlamaIndex FunctionTool stores the callable as `.fn` (older) / `._fn`
        ok = _wrap_attr(t, "fn", name, is_action)
        if not ok:
            ok = _wrap_attr(t, "_fn", name, is_action)
        if ok:
            wrapped.append(name)
    return tools_or_agent


def instrument_pydantic_ai(tools_or_agent, actions=None):
    """Auto-wrap pydantic-ai Tools (a list, or an agent exposing ``.tools``)."""
    actions = set(actions or [])
    wrapped = []
    for i, t in enumerate(_as_tool_list(tools_or_agent)):
        name = _tool_name(t, "tool_%d" % i)
        is_action = name in actions
        # pydantic-ai Tool stores the callable as `.function`
        ok = _wrap_attr(t, "function", name, is_action)
        if ok:
            wrapped.append(name)
    return tools_or_agent


def instrument(tools_or_agent, actions=None):
    """Universal one-liner: auto-instrument any supported agent so faultline can
    inject faults into its tools — a list of tools, a LangChain AgentExecutor, a
    LangGraph ToolNode / compiled graph, LlamaIndex tools, or pydantic-ai Tools.
    Idempotent (the wrapper carries a flag, so a tool is never double-wrapped).
    Returns the input.

        graph = create_react_agent(model, tools)
        fl.instrument(graph, actions=["place_order"])   # works for any framework
    """
    instrument_langchain(tools_or_agent, actions=actions)
    instrument_langgraph(tools_or_agent, actions=actions)
    instrument_llamaindex(tools_or_agent, actions=actions)
    instrument_pydantic_ai(tools_or_agent, actions=actions)
    return tools_or_agent
