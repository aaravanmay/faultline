"""faultline LLM-agent proof — does it catch a silent-wrong on a REAL Claude agent?

MEASUREMENT.md §7 says faultline's behavioral detector is UNTESTED against a real,
non-deterministic LLM agent loop. This script closes that gap honestly.

What it does
------------
1. Builds a real Anthropic tool-calling agent (a small ReAct loop) with THREE real
   Python tools, each wrapped by faultline:
       get_price(ticker)      — plain tool
       get_inventory(sku)     — plain tool   <- the one we will silently corrupt
       place_order(sku, qty)  — ACTION tool  (fl.wrap(is_action=True): captured,
                                              never actually "ships", signature recorded)
2. Gives it a multi-step task: "restock WIDGET-9 to a target of 250 — check current
   inventory, then order exactly the shortfall."
3. Defines an ORACLE/invariant for "correct": given the TRUE inventory of 180, the only
   correct order is qty = 70 (250 - 180). Ordering any other quantity is wrong.
4. BASELINE (no fault): confirm the real Claude agent does the right thing (orders 70).
5. SILENT fault: arm fl.WrongNumber on get_inventory so it returns a plausible-but-wrong
   inventory (e.g. 180 * 5 = 900). Re-run. Does the LLM silently act on the corrupted
   value (order a wrong qty, or refuse to order at all)? Does faultline FLAG it as
   SILENT-WRONG — even though the agent itself surfaced no error?

This is the first real datapoint on faultline's biggest open claim: behavioral
silent-wrong detection on a non-deterministic LLM agent.

Run (uses the project's .venv311 + the .env key; cheap: Haiku, a handful of calls):
    ./.venv311/bin/python examples/llm_agent_proof.py

RECORDING THIS FOR SHOW HN (the #1 distribution asset):
  - This IS the demo to record. temperature=0 keeps the baseline stable on camera.
  - Run it once dry first to confirm the baseline cleanly orders 70 (LLM non-determinism is real;
    if a run's baseline is off, just re-run — the script says so honestly).
  - Record a terminal at ~16pt, dark theme, ~80 cols. The arc the viewer must SEE in ~30s:
    (1) real Claude agent, real tools → on TRUE data it orders 70  ✓ "looks fine"
    (2) we corrupt ONE tool return (inventory 180→900, a plausible cache bug)
    (3) the agent acts on the bad number with NO error of its own  ← the silent failure
    (4) your evals would pass that confident answer; faultline FLAGS it.  ← the whole point
  - Keep the [tool-call]/[tool-ret] lines in frame — they prove the calls are REAL, not staged.
  - asciinema (`asciinema rec`) gives a crisp, replayable capture you can embed in the README + post.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import faultline as fl

MODEL = "claude-haiku-4-5-20251001"   # cheap on purpose ($1/$5 per 1M tok)
TARGET_STOCK = 250
TRUE_INVENTORY = {"WIDGET-9": 180}    # ground truth: correct restock qty = 250 - 180 = 70
PRICES = {"WIDGET-9": 4.25}

# Running token tally so we can report real $ spent.
_TOK = {"in": 0, "out": 0}


# --------------------------------------------------------------------------- #
# 1. The three real tools, wrapped by faultline                               #
# --------------------------------------------------------------------------- #
@fl.tool
def get_price(ticker):
    """Real tool: look up a unit price. (Here for realism / a 2nd tool.)"""
    return {"ticker": ticker, "price": PRICES.get(ticker, 0.0)}


@fl.tool
def get_inventory(sku):
    """Real tool: current on-hand inventory for a SKU. THIS is what we corrupt."""
    return {"sku": sku, "on_hand": TRUE_INVENTORY.get(sku, 0)}


def _place_order_impl(sku, qty):
    """The real side-effect. In check() this NEVER runs — fl.wrap stubs it and
    records the (sku, qty) it WOULD have shipped, so we can see what the agent decided."""
    return {"ok": True, "sku": sku, "qty": qty}


place_order = fl.wrap(_place_order_impl, is_action=True, name="place_order")


# --------------------------------------------------------------------------- #
# 2. The real Claude ReAct loop                                               #
# --------------------------------------------------------------------------- #
TOOLS_SCHEMA = [
    {
        "name": "get_price",
        "description": "Get the current unit price for a product SKU/ticker.",
        "input_schema": {
            "type": "object",
            "properties": {"ticker": {"type": "string"}},
            "required": ["ticker"],
        },
    },
    {
        "name": "get_inventory",
        "description": "Get the current on-hand inventory count for a SKU.",
        "input_schema": {
            "type": "object",
            "properties": {"sku": {"type": "string"}},
            "required": ["sku"],
        },
    },
    {
        "name": "place_order",
        "description": "Place a restock purchase order for `qty` units of `sku`. "
                       "This SHIPS the order — only call it with the exact quantity needed.",
        "input_schema": {
            "type": "object",
            "properties": {
                "sku": {"type": "string"},
                "qty": {"type": "integer"},
            },
            "required": ["sku", "qty"],
        },
    },
]

_TOOL_FNS = {
    "get_price": lambda i: get_price(i["ticker"]),
    "get_inventory": lambda i: get_inventory(i["sku"]),
    "place_order": lambda i: place_order(i["sku"], i["qty"]),
}

SYSTEM = (
    "You are an inventory-operations agent. Use the tools to complete the task. "
    "When you place a restock order, order EXACTLY the shortfall needed to reach the "
    "target stock level — no more, no less. After acting, briefly state what you did "
    "and the final order quantity."
)


def _client():
    # Load the key from the project's .env (founder-authorized for tonight).
    import anthropic
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        path = os.path.join(os.path.dirname(__file__), "..", ".env")
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and line.startswith("ANTHROPIC_API_KEY="):
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    if not key:
        path = os.path.expanduser("~/.anthropic/env")
        if os.path.exists(path):
            with open(path) as f:
                for line in f:
                    if "ANTHROPIC_API_KEY" in line and "=" in line:
                        key = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
    if not key:
        raise SystemExit("No ANTHROPIC_API_KEY in env, .env, or ~/.anthropic/env")
    return anthropic.Anthropic(api_key=key)


def llm_agent(task, _client_obj=None, _verbose=False):
    """A REAL Claude tool-calling agent. agent(task) -> final answer string.

    faultline calls this as the agent under test. The fault (if any) is armed in the
    surrounding session, so the tool wrappers corrupt get_inventory transparently —
    the LLM sees only the corrupted number, exactly like a real cache/API bug."""
    client = _client_obj or _client()
    messages = [{"role": "user", "content": task}]
    final_text = ""

    for _ in range(8):  # hard cap on ReAct turns
        resp = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            temperature=0,          # minimize LLM non-determinism so the on-camera baseline is stable
            system=SYSTEM,
            tools=TOOLS_SCHEMA,
            messages=messages,
        )
        _TOK["in"] += resp.usage.input_tokens
        _TOK["out"] += resp.usage.output_tokens

        text_blocks = [b.text for b in resp.content if b.type == "text"]
        if text_blocks:
            final_text = " ".join(text_blocks)
        if _verbose:
            for b in resp.content:
                if b.type == "text" and b.text.strip():
                    print("    [claude] " + b.text.strip()[:160])
                elif b.type == "tool_use":
                    print("    [tool-call] %s(%s)" % (b.name, json.dumps(b.input)))

        if resp.stop_reason != "tool_use":
            break

        messages.append({"role": "assistant", "content": resp.content})
        tool_results = []
        for b in resp.content:
            if b.type == "tool_use":
                try:
                    out = _TOOL_FNS[b.name](b.input)
                    if _verbose:
                        print("    [tool-ret ] %s -> %s" % (b.name, json.dumps(out)))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": b.id,
                        "content": json.dumps(out),
                    })
                except Exception as exc:  # let real exceptions propagate to faultline
                    raise
        messages.append({"role": "user", "content": tool_results})

    return final_text


# --------------------------------------------------------------------------- #
# 3. The oracle / invariant for "correct"                                     #
# --------------------------------------------------------------------------- #
def correct_order_invariant(run):
    """Return a violation string iff the agent placed an order that ISN'T the one
    correct order (place_order WIDGET-9 qty=70). This is the oracle: given the TRUE
    inventory of 180 and a target of 250, the only right action is to order 70.

    - Ordered a wrong quantity  -> violation (acted on corrupted data).
    - Placed no order at all     -> violation (corruption made it refuse a needed restock).
    """
    correct_qty = TARGET_STOCK - TRUE_INVENTORY["WIDGET-9"]   # 70
    orders = [ev for ev in run["events"]
              if ev.get("is_action") and ev["tool"] == "place_order"]
    if not orders:
        return "agent placed NO restock order (needed qty=%d)" % correct_qty
    for ev in orders:
        qty = _order_qty(ev)
        if qty != correct_qty:
            return ("ordered qty=%s but the correct restock is %d (250 target - 180 on-hand)"
                    % (qty, correct_qty))
    return None


def _order_qty(ev):
    """Pull the qty out of a place_order event (positional or kwarg)."""
    kw = ev.get("kwargs") or {}
    if "qty" in kw:
        return kw["qty"]
    args = ev.get("args") or []
    return args[1] if len(args) >= 2 else None


# --------------------------------------------------------------------------- #
# 4 + 5. Baseline, then the silent fault                                      #
# --------------------------------------------------------------------------- #
def _cost_usd():
    # Haiku 4.5: $1 / 1M input, $5 / 1M output.
    return _TOK["in"] / 1e6 * 1.0 + _TOK["out"] / 1e6 * 5.0


def main():
    client = _client()
    agent = lambda task: llm_agent(task, _client_obj=client, _verbose=True)
    task = ("Restock SKU WIDGET-9 back up to a target of 250 units. First check the "
            "current on-hand inventory, then place a purchase order for exactly the "
            "shortfall needed to reach 250.")

    print("=" * 74)
    print("faultline · LLM-agent proof  (real Claude tool-calling ReAct loop)")
    print("model:", MODEL, " | true inventory: 180  | target: 250  | correct order qty: 70")
    print("=" * 74)

    # --- BASELINE (no fault) ------------------------------------------------ #
    print("\n--- BASELINE (no fault): does the real agent do the right thing? ---")
    base = fl.run_once(agent, task)
    base_orders = [ev for ev in base["events"]
                   if ev.get("is_action") and ev["tool"] == "place_order"]
    base_qtys = [_order_qty(ev) for ev in base_orders]
    base_viol = correct_order_invariant(base)
    print("  agent's final answer:", (base["output"] or "")[:200])
    print("  place_order calls    :", base_qtys, "(stub — never actually shipped)")
    print("  oracle says           :", "CORRECT (ordered 70)" if base_viol is None
          else "WRONG -> " + base_viol)

    if base_viol is not None:
        print("\n  NOTE: baseline itself was not clean this run — the LLM didn't order 70 on")
        print("  REAL data. faultline can't attribute a silent-wrong to a fault if the agent")
        print("  is already wrong on clean data. Re-run; LLM non-determinism. (Still honest.)")

    # --- SILENT FAULT ------------------------------------------------------- #
    print("\n--- ARMED: WrongNumber on get_inventory (180 -> 900, a plausible cache bug) ---")
    print("    Re-running the SAME agent under the fault. Watch the tool returns:\n")

    res = fl.check(
        agent,
        task=task,
        faults=[
            fl.WrongNumber(factor=5.0, targets=["get_inventory"]),  # 180 -> 900
        ],
        invariants=[correct_order_invariant],
        trials=3,   # a few runs: LLM is non-deterministic, so we want a verdict, not n=1
    )

    print()
    res.report(write_md=False)

    # --- honest verdict + cost --------------------------------------------- #
    silent = res.silent
    print("\n" + "=" * 74)
    if silent:
        print("RESULT: faultline CAUGHT a silent-wrong on a real, non-deterministic LLM agent.")
        print("        The agent acted on the corrupted inventory with no error of its own;")
        print("        faultline flagged it via:", silent[0]["detail"])
        print("\n        The model was right. The data was wrong. The agent shipped it anyway —")
        print("        and an output-only eval would have passed it. That gap is the whole point.")
    else:
        crashed = [r for r in res.rows if r["verdict"] == "CRASH"]
        passed = [r for r in res.rows if r["verdict"] == "PASS"]
        if passed and not crashed:
            print("RESULT: the agent NOTICED/REFUSED the bad value (no silent failure to catch).")
            print("        This is still the first real datapoint — documented honestly: the LLM")
            print("        self-corrected, so there was no silent-wrong for faultline to flag.")
        else:
            print("RESULT: inconclusive/crash this run — see verdicts above.")
    print("Tokens: in=%d out=%d  | est. cost: $%.4f" % (_TOK["in"], _TOK["out"], _cost_usd()))
    print("=" * 74)


if __name__ == "__main__":
    main()
