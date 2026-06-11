"""A tiny example agent you can scan with zero setup.

    faultline scan faultline/examples/your_agent.py:restock_agent --task '{"sku": "A-12"}'

No suite file, no invariants — `scan` discovers the wrapped tools, breaks them,
and runs the deterministic detector. Wrap YOUR tools the same way (one
decorator each) and point `scan` at your own agent function.
"""
import faultline as fl

_TRUE_INVENTORY = {"A-12": 240}


@fl.tool
def get_inventory(sku):
    """Your real tool — wrap it with @fl.tool so faultline can intercept it."""
    return {"sku": sku, "units": _TRUE_INVENTORY.get(sku, 0)}


_orders = []


def _place_order(sku, qty):
    _orders.append((sku, qty))
    return {"status": "submitted", "sku": sku, "qty": qty}


# An action tool — captured (and stubbed during a scan) so nothing real fires.
# (name= keeps the tool's display name clean even though the function is _place_order.)
place_order = fl.wrap(_place_order, is_action=True, name="place_order")


def restock_agent(task):
    """Keep the SKU stocked at 250. Reads inventory, orders the shortfall.

    Deliberately un-guarded so a scan has something to catch — try adding the
    obvious guards (abstain on missing/empty data, sanity-bound the reading)
    and re-scan to watch it go green.
    """
    sku = task["sku"]
    units = get_inventory(sku)["units"]
    qty = max(0, 250 - units)
    if qty > 0:
        place_order(sku, qty)
    return {"sku": sku, "ordered": qty}
