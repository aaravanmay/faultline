"""Test: faultline scan — zero-oracle, zero-suite-file silent-failure check.

Proves scan (a) discovers wrapped tools from a baseline run, (b) catches a
vulnerable agent with NO hand-written invariants, (c) clears a resilient agent
(no false alarm), (d) reports [] when nothing is wrapped, and (e) the CLI gates.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import faultline as fl

passed = 0
failed = 0


def expect(name, cond):
    global passed, failed
    if cond:
        passed += 1
        print("  PASS %s" % name)
    else:
        failed += 1
        print("  FAIL %s" % name)


# ── shared wrapped tools ──────────────────────────────────────────────────
@fl.tool
def get_inventory(sku):
    return {"sku": sku, "units": 240}     # true count: 240


_orders = []


def _place_order(sku, qty):
    _orders.append((sku, qty))
    return "ok"


place_order = fl.wrap(_place_order, is_action=True)


# ── a VULNERABLE agent (no guards, no try/except) ─────────────────────────
def vuln_agent(task):
    units = get_inventory("A-12")["units"]
    qty = max(0, 250 - units)
    if qty > 0:
        place_order("A-12", qty)
    return {"ordered": qty}


# ── a RESILIENT agent (guards data + tool failures) ───────────────────────
def resilient_agent(task):
    try:
        data = get_inventory("A-12")
    except Exception:
        return {"ordered": 0, "flagged": "inventory tool failed"}
    if not data or "units" not in data:
        return {"ordered": 0, "flagged": "no inventory data"}
    units = data["units"]
    if not (0 <= units <= 500):
        return {"ordered": 0, "flagged": "implausible reading"}
    qty = max(0, 250 - units)
    if qty > 50:
        return {"ordered": 0, "flagged": "exceeds cap"}
    if qty > 0:
        try:
            place_order("A-12", qty)
        except Exception:
            return {"ordered": 0, "flagged": "order failed"}
    return {"ordered": qty}


# ── an agent with NO wrapped tools ────────────────────────────────────────
def bare_agent(task):
    return {"ordered": 10}


# 1. discovery
tools, _ = fl.discover_tools(vuln_agent, {})
expect("discover_tools finds the wrapped tool", "get_inventory" in tools)

# 2. zero-oracle catch on the vulnerable agent
result, tool_names = fl.scan(vuln_agent, {}, trials=3)
expect("scan returns the discovered tool names", "get_inventory" in tool_names)
bad = [r for r in result.rows if r["verdict"] in ("FAIL", "CRASH")]
expect("scan catches the vulnerable agent with NO invariants", len(bad) >= 1)

# 3. resilient agent comes back clean (no false alarm)
res2, _ = fl.scan(resilient_agent, {}, trials=3)
bad2 = [r for r in res2.rows if r["verdict"] in ("FAIL", "CRASH")]
expect("scan clears a resilient agent (no false alarm)", len(bad2) == 0)

# 4. nothing wrapped -> empty discovery (don't silently pass a vacuous run)
_, bare_tools = fl.scan(bare_agent, {}, trials=2)
expect("agent with no wrapped tools -> empty discovery", bare_tools == [])

# 5. CLI: faultline scan FILE.py:agent gates on a vulnerable agent
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
agent_file = os.path.join(HERE, "_scan_tmp_agent.py")
with open(agent_file, "w") as f:
    f.write(
        "import faultline as fl\n"
        "@fl.tool\n"
        "def get_inv(sku):\n"
        "    return {'units': 240}\n"
        "_o = []\n"
        "def _po(sku, qty):\n"
        "    _o.append((sku, qty)); return 'ok'\n"
        "place_order = fl.wrap(_po, is_action=True)\n"
        "def agent(task):\n"
        "    u = get_inv('A')['units']\n"
        "    q = max(0, 250 - u)\n"
        "    if q > 0: place_order('A', q)\n"
        "    return {'ordered': q}\n"
    )
try:
    env = dict(os.environ, PYTHONPATH=REPO)
    p = subprocess.run(
        [sys.executable, "-m", "faultline.cli", "scan", agent_file + ":agent", "--task", "{}"],
        capture_output=True, text=True, env=env,
    )
    expect("CLI scan exits non-zero on a vulnerable agent", p.returncode == 1)
    expect("CLI scan names the wrapped tool", "get_inv" in p.stdout)
    # bare agent -> usage error (exit 2), not a vacuous green
    bare_file = os.path.join(HERE, "_scan_bare_agent.py")
    with open(bare_file, "w") as bf:
        bf.write("def agent(task):\n    return {'ordered': 10}\n")
    p2 = subprocess.run(
        [sys.executable, "-m", "faultline.cli", "scan", bare_file + ":agent"],
        capture_output=True, text=True, env=env,
    )
    expect("CLI scan refuses an agent with no wrapped tools (exit 2)", p2.returncode == 2)
    os.remove(bare_file)
finally:
    if os.path.exists(agent_file):
        os.remove(agent_file)

print("\n%d passed, %d failed" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
